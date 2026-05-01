extends Control

func _on_back_button_pressed() -> void:
	SceneRouter.go_main_menu()

func _on_host_button_pressed() -> void:
	GameState.is_host = true
	SceneRouter.go_battle() # 现在先跳占位，后面这里改成 LobbyRoom

func _on_join_button_pressed() -> void:
	GameState.is_host = false
	SceneRouter.go_battle() # 现在先跳占位，后面这里改成 LobbyRoom
