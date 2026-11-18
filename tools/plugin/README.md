# tools/plugin

The native plugin API's test (`runtime/plugin/`).

| File | What it is |
|---|---|
| `probe.sh` | Builds `probe_plugin.c` as the mod `plugin-probe` (`build/mods/plugin-probe/plugin/`) and runs `build/mkw --probe-plugin` with it on: a call through main's PLT reaches the plugin's override by name, an indirect call to the game's definition its override by address |
| `probe_plugin.c` | The plugin it loads: one of each hook, chained to the runtime's own handler and to the game's original. Also the smallest example of a plugin |
