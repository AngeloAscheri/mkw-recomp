// NVN's alpha test as a SPIR-V rewrite of the fragment shader, split from vk_spirv_patch.c (see vk_spirv_patch.h).
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "vk.h"
#include "vk_spirv_patch.h"

// NVN's alpha test (nvnColorStateSetAlphaTest, nvnCommandBufferSetAlphaRef): a fragment whose colour output 0 alpha
// fails `alpha FUNC ref` is discarded. The countdown's numbers enter with blending off and the alpha test on; without
// it their transparent texels (white, alpha 0) drew a white square (sq5, 06/11/2026). As eden-nx2 does (idea only,
// GPL: shader_recompiler/backend/spirv/emit_spirv_special.cpp AlphaTest), the test goes before every OpReturn of the
// entry point, with func and ref baked in (GKey.alpha_func / alpha_ref). func: VkCompareOp. NULL when the module has no
// float vec4 Output at Location 0 or another layout.
uint32_t *spirv_alpha_test(const uint32_t *w, uint64_t n, int func, float ref, uint64_t *out_n) {
    enum { OP_TYPE_BOOL = 20, OP_CONSTANT_FALSE = 42, OP_FUNCTION_END = 56, OP_LOAD = 61, OP_COMPOSITE_EXTRACT = 81,
           OP_SELECTION_MERGE = 247, OP_LABEL = 248, OP_BRANCH_CONDITIONAL = 250, OP_KILL = 252, OP_RETURN = 253,
           OP_TERMINATE_INVOCATION = 4416 };
    static const uint16_t cmp_op[8] = {0, 184, 180, 188, 186, 182, 190, 0};   // VkCompareOp -> OpFOrd*
    if (func == VK_COMPARE_OP_ALWAYS || func < 0 || func > 7 || n < 5) return NULL;
    uint32_t bound = w[3], entry = 0, f32 = 0, boolt = 0, out0 = 0, v4 = 0, nret = 0;
    uint32_t vars[64][2], ptrs[64][2], vecs[64][3];   // (id, pointer type), (id, pointee), (id, comp, count)
    int nvars = 0, nptrs = 0, nvecs = 0;
    uint64_t fn_at = 0, fn_lo = 0, fn_hi = 0;
    uint32_t loc0[16];
    int nloc0 = 0;
    for (uint64_t i = 5; i < n;) {
        uint32_t op = w[i] & 0xffff, len = w[i] >> 16;
        if (!len || i + len > n) return NULL;
        const uint32_t *a = w + i + 1;
        if (op == SPV_OP_ENTRY_POINT && len >= 3 && !entry) entry = a[1];
        else if (op == SPV_OP_DECORATE && len == 4 && a[1] == SPV_DEC_LOCATION && a[2] == 0 && nloc0 < 16) loc0[nloc0++] = a[0];
        else if (op == SPV_OP_TYPE_FLOAT && len == 3 && a[1] == 32) f32 = a[0];
        else if (op == OP_TYPE_BOOL && len == 2) boolt = a[0];
        else if (op == SPV_OP_TYPE_VECTOR && len == 4 && nvecs < 64) vecs[nvecs][0] = a[0], vecs[nvecs][1] = a[1], vecs[nvecs++][2] = a[2];
        else if (op == SPV_OP_TYPE_POINTER && len == 4 && a[1] == SPV_SC_OUTPUT && nptrs < 64) ptrs[nptrs][0] = a[0], ptrs[nptrs++][1] = a[2];
        else if (op == SPV_OP_VARIABLE && len >= 4 && a[2] == SPV_SC_OUTPUT && nvars < 64) vars[nvars][0] = a[1], vars[nvars++][1] = a[0];
        else if (op == SPV_OP_FUNCTION && !fn_at) fn_at = i;
        if (op == SPV_OP_FUNCTION && len == 5 && a[1] == entry) fn_lo = i;
        if (op == OP_FUNCTION_END && fn_lo && !fn_hi) fn_hi = i;
        if (op == OP_RETURN && fn_lo && !fn_hi) nret++;
        i += len;
    }
    for (int k = 0; k < nvars && !out0; k++)
        for (int j = 0; j < nloc0; j++)
            if (vars[k][0] == loc0[j])
                for (int p = 0; p < nptrs; p++)
                    if (ptrs[p][0] == vars[k][1])
                        for (int v = 0; v < nvecs; v++)
                            if (vecs[v][0] == ptrs[p][1] && vecs[v][1] == f32 && vecs[v][2] == 4) out0 = vars[k][0], v4 = vecs[v][0];
    if (!out0 || !f32 || !fn_at || !fn_lo || !fn_hi || !nret) return NULL;
    uint32_t kill = w[1] >= 0x10600 ? OP_TERMINATE_INVOCATION : OP_KILL;
    // Types and constants go before the first function: bool if missing, the reference (or false for NEVER).
    uint32_t head[8], nh = 0, cref = bound++, cfalse = 0;
    if (!boolt) boolt = bound++, head[nh++] = 2u << 16 | OP_TYPE_BOOL, head[nh++] = boolt;
    uint32_t refbits;
    memcpy(&refbits, &ref, 4);
    head[nh++] = 4u << 16 | SPV_OP_CONSTANT, head[nh++] = f32, head[nh++] = cref, head[nh++] = refbits;
    if (func == VK_COMPARE_OP_NEVER) cfalse = bound++, head[nh++] = 3u << 16 | OP_CONSTANT_FALSE, head[nh++] = boolt, head[nh++] = cfalse;
    const uint32_t per = 4 + 5 + (cfalse ? 0 : 5) + 3 + 4 + 2 + 1 + 2;   // load, extract, compare, merge, branch, labels, kill
    uint32_t *o = malloc((n + nh + (uint64_t)nret * per) * 4);
    if (!o) return NULL;
    uint64_t at = 0;
    for (uint64_t i = 0; i < n;) {
        uint32_t op = i < 5 ? 0 : w[i] & 0xffff, len = i < 5 ? 5 : w[i] >> 16;
        if (i == fn_at) memcpy(o + at, head, nh * 4), at += nh;
        if (op == OP_RETURN && i > fn_lo && i < fn_hi) {
            uint32_t c = bound++, al = bound++, t = cfalse ? cfalse : bound++, ok = bound++, kl = bound++;
            o[at++] = 4u << 16 | OP_LOAD, o[at++] = v4, o[at++] = c, o[at++] = out0;
            o[at++] = 5u << 16 | OP_COMPOSITE_EXTRACT, o[at++] = f32, o[at++] = al, o[at++] = c, o[at++] = 3;
            if (!cfalse) o[at++] = 5u << 16 | cmp_op[func], o[at++] = boolt, o[at++] = t, o[at++] = al, o[at++] = cref;
            o[at++] = 3u << 16 | OP_SELECTION_MERGE, o[at++] = ok, o[at++] = 0;
            o[at++] = 4u << 16 | OP_BRANCH_CONDITIONAL, o[at++] = t, o[at++] = ok, o[at++] = kl;
            o[at++] = 2u << 16 | OP_LABEL, o[at++] = kl;
            o[at++] = 1u << 16 | kill;
            o[at++] = 2u << 16 | OP_LABEL, o[at++] = ok;
        }
        memcpy(o + at, w + i, len * 4), at += len;
        i += len;
    }
    o[3] = bound;
    *out_n = at;
    return o;
}
