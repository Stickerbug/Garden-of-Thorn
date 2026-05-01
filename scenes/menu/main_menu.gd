extends Control

func _on_local_multiplayer_button_pressed() -> void:
	GameState.match_mode = GameState.MatchMode.LOCAL_LAN
	GameState.reset_match_data()
	SceneRouter.go_lobby_menu()

func _on_training_button_pressed() -> void:
	GameState.match_mode = GameState.MatchMode.TRAINING
	GameState.reset_match_data()
	SceneRouter.go_training_select()

func _on_settings_button_pressed() -> void:
	SceneRouter.go_settings()

func _on_quit_button_pressed() -> void:
	get_tree().quit()
