extends Node

const BOOT_SCENE := "res://scenes/boot/boot.tscn"
const MAIN_MENU_SCENE := "res://scenes/menu/main_menu.tscn"
const LOBBY_MENU_SCENE := "res://scenes/menu/lobby_menu.tscn"
const TRAINING_SELECT_SCENE := "res://scenes/training/training_select.tscn"
const DRAFT_SELECT_SCENE := "res://scenes/draft/draft_select.tscn"
const BATTLE_SCENE := "res://scenes/battle/battle.tscn"
const VICTORY_SCENE := "res://scenes/result/victory.tscn"
const DEFEAT_SCENE := "res://scenes/result/defeat.tscn"
const SETTINGS_SCENE := "res://scenes/settings/settings_menu.tscn"

func go_to(path: String) -> void:
	var err := get_tree().change_scene_to_file(path)
	if err != OK:
		push_error("Scene change failed: %s, error=%s" % [path, err])

func go_boot() -> void:
	go_to(BOOT_SCENE)

func go_main_menu() -> void:
	go_to(MAIN_MENU_SCENE)

func go_lobby_menu() -> void:
	go_to(LOBBY_MENU_SCENE)

func go_training_select() -> void:
	go_to(TRAINING_SELECT_SCENE)

func go_draft_select() -> void:
	go_to(DRAFT_SELECT_SCENE)

func go_battle() -> void:
	go_to(BATTLE_SCENE)

func go_victory() -> void:
	go_to(VICTORY_SCENE)

func go_defeat() -> void:
	go_to(DEFEAT_SCENE)

func go_settings() -> void:
	go_to(SETTINGS_SCENE)
