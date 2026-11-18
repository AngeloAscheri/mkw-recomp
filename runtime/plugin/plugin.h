// Native plugins of the enabled mods (plugin.c; the API they get: mkw_plugin.h).
#pragma once

void plugins_load(void);          // before ldr_load: each enabled mod's plugin/ libraries, their mkw_plugin_init
void plugins_game_loaded(void);   // after ldr_load, before hostfn_seal: the plugins' on_game_loaded callbacks
void plugins_started(void);       // after hostfn_seal: no more address overrides
