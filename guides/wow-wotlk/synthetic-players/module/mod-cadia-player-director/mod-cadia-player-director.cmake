if(NOT MOD_PLAYERBOTS_FOUND)
  message(FATAL_ERROR "mod-cadia-player-director requires mod-playerbots")
endif()

ModuleNameToVariable(mod-playerbots PLAYERBOTS_MODULE_VARIABLE)
if(${PLAYERBOTS_MODULE_VARIABLE} STREQUAL "disabled")
  message(FATAL_ERROR "mod-cadia-player-director requires mod-playerbots to be enabled")
endif()

ModuleNameToVariable(mod-cadia-player-director DIRECTOR_MODULE_VARIABLE)
if(${DIRECTOR_MODULE_VARIABLE} STREQUAL "dynamic")
  message(FATAL_ERROR "mod-cadia-player-director must use static module linkage")
endif()
