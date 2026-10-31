/*
 * Minimal VapourSynth VMAF-compatible plugin for CHEN-V.
 * Only implements vmaf.Metric(reference, distorted, feature=0) with PSNR-Y.
 * This is exactly what vs-rife's skip=True uses.
 */
#include <stdint.h>
#include <stddef.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

#include "VapourSynth4.h"

typedef struct MetricData {
    VSNode *reference;
    VSNode *distorted;
    VSVideoInfo vi;
} MetricData;

static double psnr_y(const VSFrame *ref, const VSFrame *dist,
                     const VSVideoFormat *fmt, const VSAPI *vsapi) {
    const int w = vsapi->getFrameWidth(ref, 0);
    const int h = vsapi->getFrameHeight(ref, 0);
    if (w <= 0 || h <= 0)
        return 0.0;
    const ptrdiff_t rs = vsapi->getStride(ref, 0);
    const ptrdiff_t ds = vsapi->getStride(dist, 0);
    const uint8_t *rp = vsapi->getReadPtr(ref, 0);
    const uint8_t *dp = vsapi->getReadPtr(dist, 0);
    const int bps = fmt->bytesPerSample;
    const int bits = fmt->bitsPerSample;
    const double maxv = (double)((1 << bits) - 1);
    double sum = 0.0;
    int x, y;

    for (y = 0; y < h; y++) {
        const uint8_t *rrow = rp + (ptrdiff_t)y * rs;
        const uint8_t *drow = dp + (ptrdiff_t)y * ds;
        if (bps == 1) {
            for (x = 0; x < w; x++) {
                double d = (double)rrow[x] - (double)drow[x];
                sum += d * d;
            }
        } else if (bps == 2) {
            const uint16_t *r16 = (const uint16_t *)rrow;
            const uint16_t *d16 = (const uint16_t *)drow;
            for (x = 0; x < w; x++) {
                double d = (double)r16[x] - (double)d16[x];
                sum += d * d;
            }
        } else {
            const uint32_t *r32 = (const uint32_t *)rrow;
            const uint32_t *d32 = (const uint32_t *)drow;
            for (x = 0; x < w; x++) {
                double d = (double)r32[x] - (double)d32[x];
                sum += d * d;
            }
        }
    }
    {
        double mse = sum / ((double)w * (double)h);
        if (mse <= 1e-12)
            return 100.0;
        return 10.0 * log10((maxv * maxv) / mse);
    }
}

static const VSFrame *VS_CC metricGetFrame(int n, int activationReason, void *instanceData,
                                           void **frameData, VSFrameContext *frameCtx,
                                           VSCore *core, const VSAPI *vsapi) {
    MetricData *d = (MetricData *)instanceData;
    (void)frameData;

    if (activationReason == arInitial) {
        vsapi->requestFrameFilter(n, d->reference, frameCtx);
        vsapi->requestFrameFilter(n, d->distorted, frameCtx);
        return NULL;
    }
    if (activationReason != arAllFramesReady)
        return NULL;

    {
        const VSFrame *ref = vsapi->getFrameFilter(n, d->reference, frameCtx);
        const VSFrame *dist = vsapi->getFrameFilter(n, d->distorted, frameCtx);
        if (!ref || !dist) {
            if (ref) vsapi->freeFrame(ref);
            if (dist) vsapi->freeFrame(dist);
            return NULL;
        }
        {
            double score = psnr_y(ref, dist, &d->vi.format, vsapi);
            VSFrame *out = vsapi->copyFrame(ref, core);
            if (out) {
                VSMap *props = vsapi->getFramePropertiesRW(out);
                vsapi->mapSetFloat(props, "psnr_y", score, maReplace);
            }
            vsapi->freeFrame(ref);
            vsapi->freeFrame(dist);
            return out;
        }
    }
}

static void VS_CC metricFree(void *instanceData, VSCore *core, const VSAPI *vsapi) {
    MetricData *d = (MetricData *)instanceData;
    (void)core;
    if (d->reference) vsapi->freeNode(d->reference);
    if (d->distorted) vsapi->freeNode(d->distorted);
    free(d);
}

static void VS_CC metricCreate(const VSMap *in, VSMap *out, void *userData,
                               VSCore *core, const VSAPI *vsapi) {
    int err1 = 0, err2 = 0;
    MetricData *d;
    VSNode *ref, *dist;
    const VSVideoInfo *rvi;
    const VSVideoInfo *dvi;
    VSFilterDependency deps[2];
    (void)userData;

    ref = vsapi->mapGetNode(in, "reference", 0, &err1);
    dist = vsapi->mapGetNode(in, "distorted", 0, &err2);
    if (err1 || !ref) {
        vsapi->mapSetError(out, "Metric: missing reference clip");
        if (ref) vsapi->freeNode(ref);
        if (dist) vsapi->freeNode(dist);
        return;
    }
    if (err2 || !dist) {
        vsapi->mapSetError(out, "Metric: missing distorted clip");
        vsapi->freeNode(ref);
        if (dist) vsapi->freeNode(dist);
        return;
    }

    rvi = vsapi->getVideoInfo(ref);
    dvi = vsapi->getVideoInfo(dist);
    if (!rvi || !dvi || rvi->width != dvi->width || rvi->height != dvi->height ||
        rvi->format.colorFamily != dvi->format.colorFamily ||
        rvi->format.bitsPerSample != dvi->format.bitsPerSample ||
        rvi->format.subSamplingW != dvi->format.subSamplingW ||
        rvi->format.subSamplingH != dvi->format.subSamplingH) {
        vsapi->mapSetError(out, "Metric: reference and distorted clips must have the same format and size");
        vsapi->freeNode(ref);
        vsapi->freeNode(dist);
        return;
    }

    d = (MetricData *)calloc(1, sizeof(MetricData));
    if (!d) {
        vsapi->mapSetError(out, "Metric: out of memory");
        vsapi->freeNode(ref);
        vsapi->freeNode(dist);
        return;
    }
    d->reference = ref;
    d->distorted = dist;
    d->vi = *rvi;
    if (dvi->numFrames < d->vi.numFrames)
        d->vi.numFrames = dvi->numFrames;

    deps[0].source = ref;
    deps[0].requestPattern = rpGeneral;
    deps[1].source = dist;
    deps[1].requestPattern = rpGeneral;
    vsapi->createVideoFilter(out, "Metric", &d->vi, metricGetFrame, metricFree,
                             fmParallel, deps, 2, d, core);
}

VS_EXTERNAL_API(void) VapourSynthPluginInit2(VSPlugin *plugin, const VSPLUGINAPI *vspapi) {
    vspapi->configPlugin("com.holywu.vmaf", "vmaf",
                         "Minimal PSNR metric for CHEN-V RIFE skip",
                         VS_MAKE_VERSION(1, 0), VAPOURSYNTH_API_VERSION,
                         0, plugin);
    vspapi->registerFunction("Metric",
                             "reference:vnode;"
                             "distorted:vnode;"
                             "feature:int:opt;",
                             "clip:vnode;",
                             metricCreate, NULL, plugin);
}
