# runtime/plugin

Native plugins: shared libraries a mod ships in its `plugin/` folder (`mods/<mod>/plugin/*.so` on Linux, `*.dll` on
Windows), loaded at start when the player has the mod enabled on the Mods page (or with `--mod <name>`), before the
game code loads. The API is generic: overrides by symbol and by guest address, a callback once the game is loaded,
calls into guest code; what a plugin does with them is its own business, and nothing of it lives in this repo.

| File | What it is |
|---|---|
| `mkw_plugin.h` | The API, version 1: the one header a plugin includes (it links against nothing of mkw-recomp). Rules for threads, guest memory and what each hook may do are in its comments |
| `plugin.c`, `plugin.h` | The loader: each enabled mod's `plugin/` libraries, their `mkw_plugin_init`, the API table, the game-loaded callbacks. A plugin that declines or fails to load is logged and shown to the player in a box |

How the hooks reach the game: an override by symbol goes in as the loader binds the modules (`core/boot/loader.c`,
the game's own definition kept as its original); an override by address empties the function's slot of the dispatch
table (`cpu/dispatch.c` `rt_dispatch_override`), so every indirect call to it lands in the plugin, while direct calls
inside translated code stay direct. The test is `tools/plugin/probe.sh` (`build/mkw --probe-plugin`).
