// The plugin `build/mkw --probe-plugin` loads (tools/plugin/probe.sh builds it into build/mods/plugin-probe/plugin/):
// one of each hook of mkw_plugin.h, with answers the probe (runtime/probes/plugin_probe.c) recognises. Also the
// smallest example of a plugin: it includes only mkw_plugin.h and links against nothing of mkw-recomp.
#include "mkw_plugin.h"

#define TICK "_ZN2nn2os13GetSystemTickEv"

static const MkwPluginApi *api;
static MkwGuestFn tick_stock;
static uint64_t tick_guest;

// Every reference of the game to TICK: the runtime's own replacement if it has one, else the game's own definition,
// with a mark in the top bits.
static void tick_hook(MkwCpu *c) {
    if (tick_stock) tick_stock(c);
    else api->call_original(c);
    c->x[0] = (c->x[0] & 0xffffffffull) | 0x5eed000100000000ull;
}

// An indirect call to the game's own definition of TICK: its original, with another mark.
static void tick_at(MkwCpu *c) {
    uint64_t t = api->call_original(c);
    c->x[0] = (t & 0xffffffffull) | 0x5eed000200000000ull;
}

static void loaded(void *user) {
    (void)user;
    tick_guest = api->guest_symbol(TICK);
    api->log("probe plugin: game %s loaded, main at %#llx, %s defined at %#llx", api->game_version,
             (unsigned long long)api->module_base("main"), TICK, (unsigned long long)tick_guest);
    if (tick_guest) api->override_address(tick_guest, tick_at);
}

MKW_PLUGIN_EXPORT int mkw_plugin_init(const MkwPluginApi *a, uint32_t version, const char **message) {
    if (version < 1 || a->size < sizeof(MkwPluginApi)) {
        *message = "needs plugin API 1";
        return 1;
    }
    api = a;
    tick_stock = api->stock(TICK);   // NULL: the game's own definition runs (call_original)
    api->override_symbol(TICK, tick_hook);
    api->on_game_loaded(loaded, 0);
    api->log("probe plugin: init in %s (runtime %s, %d modules loaded)", api->mod_dir, api->port_version,
             api->guest_modules());
    return 0;
}
