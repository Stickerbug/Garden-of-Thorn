extends Node

enum MatchMode {
	LOCAL_LAN,
	TRAINING
}

var match_mode: MatchMode = MatchMode.TRAINING
var player_name: String = "Player"
var is_host: bool = false
var selected_deck_id: String = ""
var chosen_cards: Array[String] = []

func reset_match_data() -> void:
	is_host = false
	selected_deck_id = ""
	chosen_cards.clear()
