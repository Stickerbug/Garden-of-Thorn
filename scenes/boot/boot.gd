extends Control

@onready var loading_label: Label = $CenterContainer/VBoxContainer/LoadingLabel
@onready var progress_bar: ProgressBar = $CenterContainer/VBoxContainer/ProgressBar

func _ready() -> void:
	loading_label.text = "正在初始化..."
	progress_bar.value = 0

	await get_tree().process_frame
	progress_bar.value = 25
	await get_tree().create_timer(0.15).timeout

	progress_bar.value = 60
	await get_tree().create_timer(0.15).timeout

	progress_bar.value = 100
	await get_tree().create_timer(0.10).timeout

	SceneRouter.go_main_menu()
