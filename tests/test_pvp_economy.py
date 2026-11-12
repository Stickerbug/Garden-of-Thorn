from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json

import pytest

import db
import account_integrity as integrity
import pvp_economy as economy
import battle_pass


NOW=datetime(2026,9,1,4,tzinfo=timezone.utc)


@pytest.fixture
def accounts(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'economy.sqlite3'))
    db.init_db()
    with db.get_db_connection() as conn:
        for uid in range(1,9):
            conn.execute('''INSERT INTO users(id,username,username_lower,password_hash,created_at,gr_season_id)
                VALUES (?,?,?,?,?,?)''',(uid,f'eco{uid}',f'eco{uid}','unused',integrity._iso(NOW),db.current_gr_season()['id']))
            integrity.initialize_user_conn(conn,uid,NOW)
        conn.commit()


def game(ids=(1,2),win=0,*,key=None,early=False,ranked=False,day=0,**extra):
    mode='2v2' if len(ids)==4 else '1v1'
    teams=[[0,1],[2,3]] if len(ids)==4 else [[0],[1]]
    ended=NOW+timedelta(days=day)
    data={'mode':mode,'match_type':'ranked' if ranked else 'casual',
          'match_mode':f'{"ranked" if ranked else "casual"}_{mode}','player_ids':list(ids),
          'players':[f'eco{uid}' for uid in ids],'teams':teams,'winner_index':win,
          'winner_user_ids':[] if win==-1 else [ids[index] for index in teams[win]],
          'result':'draw' if win==-1 else 'win','valid_for_stats':True,'valid_for_ranking':ranked,
          'started_at':integrity._iso(ended-timedelta(seconds=10 if early else 300)),
          'ended_at':integrity._iso(ended),'duration_seconds':10 if early else 300,'ended_by_surrender':early}
    if key: data['match_key']=key
    data.update(extra)
    return db.save_match_summary(data),data


def profile(uid):
    with db.get_db_connection() as conn:
        return economy.profile_conn(conn,uid)


def award(ids=(1,2),win=0,**kwargs):
    mid,data=game(ids,win,**kwargs)
    return db.award_match_thorn_dew(mid,data,award_time=data['ended_at'])


def balances():
    with db.get_db_connection() as conn:
        return [row[0] for row in conn.execute('SELECT thorn_dew_free FROM users ORDER BY id')]


@pytest.mark.parametrize('ranked',[True,False])
@pytest.mark.parametrize('ids',[(1,2),(1,2,3,4)])
def test_newcomer_base_rewards_and_no_title_double_multiplier(accounts,ids,ranked):
    result=award(ids,ranked=ranked)
    amounts={row['user_id']:row['amount'] for row in result['awarded']}
    expected_win=220 if ranked else 164  # casual keeps 75% of the ranked result.
    expected_lose=120 if ranked else 90
    assert amounts[1]==expected_win
    assert amounts[ids[-1]]==expected_lose
    assert profile(1)['valid_games']==1
    assert profile(1)['win_streak']==1


def test_settlement_awards_battle_pass_xp(accounts):
    # 通行证经验（2026-11-11）：Min{40, ceil(秒/10), 回合×5}，胜方 ×1.5。
    result=award(rounds=4)  # 300 秒 → 30，回合 4×5=20 → 取 20；胜方 30
    by_uid={row['user_id']:row['xp'] for row in result['xp_awarded']}
    assert by_uid=={1:30,2:20}
    # base_xp 记的是「本局基准经验」，胜方的 1.5 倍已折进基准（普通账号倍率为 1）。
    assert [row['base_xp'] for row in result['xp_awarded']]==[30,20]
    with db.get_db_connection() as conn:
        rows=conn.execute('SELECT user_id,xp,source FROM battle_pass_xp_ledger ORDER BY user_id').fetchall()
    assert [(row['user_id'],row['xp'],row['source']) for row in rows]==[
        (1,30,'match'),(2,20,'match'),
    ]


def test_special_mode_match_still_awards_battle_pass_xp(accounts):
    # 特殊模式/不计分对局：荆露不发，但通行证经验照发（需求 2026-11-12）。
    result=award(rounds=5,valid_for_stats=False,valid_for_ranking=False,
                 ranking_invalid_reason='special_mode')
    assert result['awarded']==[]
    assert result['skipped']=='special_mode'
    by_uid={row['user_id']:row['xp'] for row in result['xp_awarded']}
    assert by_uid=={1:38,2:25}  # 回合 5×5=25，胜方 ×1.5 = 37.5 四舍五入 → 38
    with db.get_db_connection() as conn:
        rows=conn.execute('SELECT user_id,xp,source FROM battle_pass_xp_ledger ORDER BY user_id').fetchall()
    assert [(row['user_id'],row['xp'],row['source']) for row in rows]==[
        (1,38,'match'),(2,25,'match'),
    ]


def test_ai_match_awards_no_battle_pass_xp(accounts):
    # 与 Phelren 的对战不计通行证经验（也不发荆露）：结算入口直接跳过。
    result=award(rounds=6,ai_match=True,match_kind='phelren')
    assert result['skipped']=='phelren_ai_match'
    assert result['awarded']==[]
    assert result['xp_awarded']==[]
    with db.get_db_connection() as conn:
        battle_pass.ensure_pass_schema(conn)
        ledger=conn.execute('SELECT COUNT(*) FROM battle_pass_xp_ledger').fetchone()[0]
    assert ledger==0


def test_ladder_ticket_awards_report_only_actual_grants(accounts):
    first = award()
    assert first['leisure_ticket_awarded'] == [{'user_id': 1, 'amount': 1}]
    # 同一玩家每日渠道只能领取一次；后续胜利不会重复给票或重复播动画。
    second = award()
    assert second['leisure_ticket_awarded'] == []


def test_bonus_tenth_game_and_title_twentieth_boundaries(accounts):
    # 2026-10-02 新口径：增幅×2 不再按总局数（旧前10局），而是「从未达 rare
    # 且前 20 个计分局」——本测试走 casual award（不计 rank_newbie_games），
    # 新人零计分局 → 恒 ×2；is_newcomer（称号口径）仍按 20 总局。
    for n in range(1,22):
        result=award(win=-1,day=n)
        assert result['awarded'][0]['amount']==90
        assert profile(1)['is_newcomer']==(n<20)
    assert profile(1)['title_remaining']==0


def test_win_streak_caps_and_draw_loss_reset(accounts):
    for n in range(12):
        result=award(day=n)
        assert result['awarded'][0]['streak_bonus']==min(n+1,10)*10
    award(win=-1,day=12)
    assert profile(1)['win_streak']==0
    assert award(day=13)['awarded'][0]['streak_bonus']==10
    award(win=1,day=14)
    assert profile(1)['win_streak']==0


def test_early_surrender_no_rewards_and_breaks_loser_streak(accounts):
    award()
    before=balances()
    result=award(win=1,early=True)
    assert result['awarded']==[]
    assert result['skipped']=='early_surrender'
    assert isinstance(result.get('leisure_ticket_awarded'), list)
    assert balances()==before
    assert profile(1)['win_streak']==0
    assert profile(2)['win_streak']==0


def test_phelren_ai_match_never_awards_or_mutates_win_streak(accounts):
    award()
    assert profile(1)['win_streak'] == 1
    before = balances()

    _, data = game()
    data.update({
        'ai_match': True,
        'match_kind': 'phelren',
        'valid_for_stats': False,
        'valid_for_ranking': False,
        'ranking_invalid_reason': 'phelren_ai_match',
    })
    result = economy.award_match(data.get('match_id') or 999999, data, award_time=data['ended_at'])

    assert result == {'awarded': [], 'xp_awarded': [], 'skipped': 'phelren_ai_match'}
    assert balances() == before
    assert profile(1)['win_streak'] == 1


@pytest.mark.parametrize('value,amount',[(60,164),(59,82),(40,82),(39,0)])
def test_reputation_applies_after_all_bonuses(accounts,value,amount):
    integrity.change_reputation(1,value-85,'test','set',now=NOW)
    assert award()['awarded'][0]['amount']==amount


def test_reconnect_retry_conflict_and_concurrent_settlement(accounts):
    mid,data=game(key='server-room:4:2')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:db.award_match_thorn_dew(mid,data,award_time=data['ended_at']),range(2)))
    assert sorted(bool(r.get('duplicate')) for r in results)==[False,True]
    assert balances()[:2]==[164,90]
    assert profile(1)['valid_games']==1
    duplicate_mid=db.save_match_summary(data)
    assert db.award_match_thorn_dew(duplicate_mid,data)['duplicate']
    assert db.award_match_thorn_dew(mid,{**data,'winner_user_ids':[2]})['skipped']=='settlement_conflict'
    assert profile(1)['win_streak']==1


def test_two_vs_two_counts_real_opponents_not_teammates(accounts):
    for n in range(8):
        # Same opponent, alternating our teammate and their teammate.
        result=award((1,2 if n%2 else 5,3,4 if n%2 else 6),win=-1)
        assert result['awarded'][0]['multiplier']==1
    assert award((1,7,3,8),win=-1)['awarded'][0]['multiplier']==.8


def test_confirmed_secondary_loses_newcomer_but_suspected_does_not(accounts):
    for uid in (1,2):
        integrity.record_identity_event(uid,'a'*64,'b'*64,now=NOW)
    assert profile(2)['reward_multiplier']==2
    for day in (1,2):
        for uid in (1,2):
            integrity.record_identity_event(uid,'a'*64,'b'*64,now=NOW+timedelta(days=day))
    assert profile(1)['reward_multiplier']==2
    assert profile(2)['linked_secondary']
    assert not profile(2)['is_newcomer']
    assert profile(2)['reward_multiplier']==1
    assert profile(2)['protected_ranked_remaining']==0
    assert award((1,2))['awarded'][0]['amount']==0


def test_first_three_ranked_losses_protected_and_preview_agrees(accounts):
    for n in range(4):
        preview=db.preview_gr_match_result('1v1',[1,2],viewer_user_id=2)
        assert (preview['viewer']['loss_delta']==0)==(n<3)
        mid,data=game(ranked=True,day=n)
        result=db.apply_gr_match_result(mid,data)
        assert (result['season_deltas']['2']==0)==(n<3)
        assert (result['total_deltas']['2']==0)==(n<3)
        assert (2 in result['newcomer_protected_user_ids'])==(n<3)
        db.apply_gr_match_result(mid,data)
        assert profile(2)['ranked_games']==n+1


def test_ranked_two_vs_two_protects_each_newcomer(accounts):
    mid,data=game((1,2,3,4),ranked=True)
    result=db.apply_gr_match_result(mid,data)
    assert result['newcomer_protected_user_ids']==[3,4]
    assert result['season_deltas']['3']==result['season_deltas']['4']==0


def test_legacy_ranked_games_do_not_reset_protection(accounts):
    with db.get_db_connection() as conn:
        conn.execute("UPDATE users SET gr_season_id='S202608',total_ranked_games=25,games_played=30 WHERE id=2")
        conn.commit()
    db.ensure_current_gr_season([2])
    assert profile(2)['ranked_games']==25
    assert profile(2)['protected_ranked_remaining']==0
    assert not profile(2)['is_newcomer']


def test_preview_does_not_write_and_matches_actual_award(accounts):
    mid,data=game()
    before=balances()
    with db.get_db_connection() as conn:
        estimated=db._estimate_match_thorn_dew_awards_for_conn(conn,mid,data,award_time=data['ended_at'])
        assert conn.execute('SELECT COUNT(*) FROM pvp_reward_settlements').fetchone()[0]==0
    assert balances()==before
    assert db.award_match_thorn_dew(mid,data,award_time=data['ended_at'])==estimated


def test_failed_settlement_rolls_back_money_and_progress(accounts,monkeypatch):
    original=integrity.reward_amount_conn
    def fail_second(conn,uid,amount):
        if uid==2: raise RuntimeError('simulated failure')
        return original(conn,uid,amount)
    monkeypatch.setattr(integrity,'reward_amount_conn',fail_second)
    with pytest.raises(RuntimeError): award()
    assert balances()==[0]*8
    assert profile(1)['valid_games']==0
    with db.get_db_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pvp_reward_settlements').fetchone()[0]==0


def test_old_currency_receipt_cannot_be_paid_again(accounts):
    mid,data=game()
    with db.get_db_connection() as conn:
        conn.execute("INSERT INTO user_currency_transactions(user_id,currency,free_delta,paid_delta,reason,source_type,source_id,balance_free_after,balance_paid_after,created_at) VALUES (1,'thorn_dew',45,0,'old','match_reward',?,45,0,?)",(f'match:{mid}:u:1:opp:old',integrity._iso(NOW)))
        conn.execute('UPDATE users SET thorn_dew_free=45 WHERE id=1')
        conn.commit()
    result=db.award_match_thorn_dew(mid,data)
    assert 1 not in [r['user_id'] for r in result['awarded']]
    assert balances()[0]==45


def test_legacy_match_dew_compensation_is_one_time(accounts):
    mid, _data = game(ids=(1, 2), day=-3)
    preview = db.compensate_legacy_match_thorn_dew(dry_run=True)
    assert preview['matches_counted'] == 1
    assert preview['players'] == 2
    assert preview['total_dew'] == 80

    confirmed = db.compensate_legacy_match_thorn_dew(dry_run=False)
    assert confirmed['players'] == 2
    assert confirmed['total_dew'] == 80
    assert balances()[:2] == [40, 40]

    again = db.compensate_legacy_match_thorn_dew(dry_run=False)
    assert again['players'] == 0
    assert again['already_compensated'] == 2
    assert balances()[:2] == [40, 40]


def test_legacy_match_dew_compensation_only_covers_valid_matches(accounts):
    game(ids=(1, 2), day=-3)
    game(ids=(3, 4), day=-3, valid_for_stats=False, ranking_invalid_reason='too_short')
    game(ids=(5, 6), day=-3, ai_match=True, match_kind='phelren')
    game(ids=(7, 8), day=-3, valid_for_ranking=False)

    preview = db.compensate_legacy_match_thorn_dew(dry_run=True)
    assert preview['matches_counted'] == 2
    assert preview['players'] == 4
    assert preview['total_dew'] == 160
    assert preview['skipped'] == {'not_valid': 1, 'phelren_ai_match': 1}

    confirmed = db.compensate_legacy_match_thorn_dew(dry_run=False)
    assert confirmed['players'] == 4
    assert confirmed['total_dew'] == 160
    assert balances()[:8] == [40, 40, 0, 0, 0, 0, 40, 40]


def test_guest_nickname_changes_use_one_repeat_bucket(accounts):
    for n in range(9):
        mid,data=game()
        data['player_ids']=[1,None]
        data['players']=['eco1',f'guest{n}']
        data['winner_user_ids']=[1]
        mid=db.save_match_summary(data)
        result=db.award_match_thorn_dew(mid,data,award_time=data['ended_at'])
        assert result['awarded'][0]['multiplier']==(1 if n<8 else .8)


def test_public_badge_has_no_private_newcomer_history(accounts):
    import app as gtn
    source={'nickname':'eco1','reputation_profile':integrity.get_reputation_profile(1)}
    fields=gtn.special_public_fields(source)
    assert fields['reputation_profile']['newcomer']=={'is_newcomer':True}
    serialized=json.dumps(fields)
    assert 'ranked_games' not in serialized
    assert 'linked_secondary' not in serialized


def test_system_newcomer_title_is_not_an_equipment_choice(accounts):
    payload,error=db.set_user_equipped_titles(1,[])
    assert error is None
    assert profile(1)['is_newcomer']
    _,error=db.set_user_equipped_titles(1,['system_newcomer'])
    assert error is not None
    assert profile(1)['is_newcomer']


def test_newcomer_requires_valid_games_below_20_and_highest_rank_below_rare(accounts):
    with db.get_db_connection() as conn:
        conn.execute("UPDATE users SET games_played=19,rank_tier=9,rank_highest_tier=9 WHERE id=1")
        conn.commit()
    assert not profile(1)['is_newcomer']
    assert profile(1)['reward_multiplier']==1

    # 当前段位不是判定依据；低当前段位且历史最高未达 rare basic 时可保有新人资格。
    with db.get_db_connection() as conn:
        conn.execute("UPDATE users SET rank_tier=1,rank_highest_tier=1,rank_newbie_games=19 WHERE id=1")
        conn.commit()
    assert profile(1)['is_newcomer']
    assert profile(1)['reward_multiplier']==2
    with db.get_db_connection() as conn:
        conn.execute("UPDATE users SET games_played=20 WHERE id=1")
        conn.commit()
    assert not profile(1)['is_newcomer']
    # 增幅仍按原 rank_newbie_games 口径，不随新人标识的场次口径改变。
    assert profile(1)['reward_multiplier']==2
    with db.get_db_connection() as conn:
        conn.execute("UPDATE users SET rank_newbie_games=20 WHERE id=1")
        conn.commit()
    assert profile(1)['reward_multiplier']==1


def _rank_row(uid):
    with db.get_db_connection() as conn:
        return dict(conn.execute('''SELECT rank_tier,rank_points,rank_streak,rank_newbie_games,
            rank_shield_armed,rank_double_armed FROM users WHERE id=?''',(uid,)).fetchone())


def test_non_newcomer_rank_unchanged_against_newcomer_but_gr_still_settles(accounts):
    with db.get_db_connection() as conn:
        conn.execute('''UPDATE users SET rank_tier=9,rank_highest_tier=9,rank_points=10,
            rank_streak=5,total_ranked_games=20,rank_double_armed=1 WHERE id=1''')
        conn.execute("UPDATE users SET total_ranked_games=3 WHERE id=2")
        conn.commit()
    preview=db.preview_gr_match_result('1v1',[1,2],viewer_user_id=1)
    assert preview['non_newcomer_protected_user_ids']==[1]
    mid,data=game(ranked=True,win=1)
    result=db.apply_gr_match_result(mid,data)
    assert result['applied']
    assert result['non_newcomer_protected_user_ids']==[1]
    assert result['rank']['after']['1']['delta']==0
    assert result['rank']['after']['1']['points']==10
    assert result['rank']['after']['1']['tier_index']==9
    assert result['rank']['after']['1']['streak']==5
    assert result['rank']['deltas']['1']==0
    assert result['rank']['after']['2']['delta']>0
    assert result['rank']['after']['2']['streak']==1
    assert result['season_deltas']['1']!=0
    assert result['total_deltas']['1']!=0
    assert _rank_row(1)=={'rank_tier':9,'rank_points':10,'rank_streak':5,'rank_newbie_games':1,
                           'rank_shield_armed':0,'rank_double_armed':0}
    assert _rank_row(2)['rank_newbie_games']==1


def test_non_newcomer_versus_non_newcomer_rank_still_changes(accounts):
    with db.get_db_connection() as conn:
        conn.execute("UPDATE users SET rank_tier=9,rank_highest_tier=9,rank_points=10,games_played=20 WHERE id IN (1,2)")
        conn.commit()
    mid,data=game(ranked=True)
    result=db.apply_gr_match_result(mid,data)
    assert result['non_newcomer_protected_user_ids']==[]
    assert result['rank']['deltas']['1']>0
    assert result['rank']['deltas']['2']<0


def test_two_vs_two_protects_only_non_newcomers_facing_newcomer(accounts):
    # 实际分组为 [1,2] 对 [3,4]：只有新人3号的对方非新人1、2号受保护。
    with db.get_db_connection() as conn:
        conn.execute("UPDATE users SET rank_tier=9,rank_highest_tier=9,rank_points=10,rank_streak=2 WHERE id IN (1,2)")
        # 4号当前已掉到低段，但历史最高达到过 rare basic，仍是新人3号的非新人队友。
        conn.execute("UPDATE users SET rank_tier=1,rank_highest_tier=9,rank_points=10,rank_streak=2 WHERE id=4")
        conn.commit()
    mid,data=game((1,2,3,4),ranked=True,win=1)
    result=db.apply_gr_match_result(mid,data)
    assert result['non_newcomer_protected_user_ids']==[1,2]
    for uid in (1,2):
        assert result['rank']['deltas'][str(uid)]==0
        assert _rank_row(uid)['rank_tier']==9
        assert _rank_row(uid)['rank_points']==10
        assert _rank_row(uid)['rank_streak']==2
    assert 3 not in result['non_newcomer_protected_user_ids']
    assert 4 not in result['non_newcomer_protected_user_ids']
    assert result['rank']['deltas']['3']>0
    assert result['rank']['deltas']['4']>0
    assert db.preview_gr_match_result('2v2',[1,2,3,4])['non_newcomer_protected_user_ids']==[1,2]


def test_frontend_shows_newcomer_and_current_economy_rules():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'static/js/game.js').read_text(encoding='utf-8')
    assert "profile?.newcomer?.is_newcomer === true" in source
    assert '未达到 rare basic 才显示新人标识' in source
    assert '前20个天梯计分局' in source
    assert 'gr.non_newcomer_protected_user_ids' in source
    assert '与新人对战：非新人段位分不变' in source
    assert '胜利100，失败或平局60' in source


def test_rating_rebuild_keeps_original_newcomer_protection(accounts):
    mid,data=game(ranked=True)
    result=db.apply_gr_match_result(mid,data)
    assert result['season_deltas']['2']==0
    for _ in range(2):
        db.rebuild_gr_from_matches(dry_run=False)
        with db.get_db_connection() as conn:
            stored=json.loads(conn.execute('SELECT summary_json FROM matches WHERE id=?',(mid,)).fetchone()[0])
            assert stored['gr_result']['newcomer_protected_user_ids']==[2]
            assert stored['gr_result']['season_deltas']['2']==0


def _latest_reason(uid):
    with db.get_db_connection() as conn:
        return conn.execute("SELECT reason,free_delta FROM user_currency_transactions"
                            " WHERE user_id=? AND source_type='match_reward'"
                            " ORDER BY id DESC LIMIT 1",(uid,)).fetchone()


def test_zero_reward_reasons_say_why(accounts):
    """反馈 GB-194：0 奖励的明细要写明原因，不能再只打印奖励公式。"""
    award(win=1,early=True)
    reason,delta=_latest_reason(1)
    assert delta==0
    assert '对局过早结束' in reason

    award(ids=(3,4),win=0)  # 先给 3/4 各一局正常奖励，作为对照
    with db.get_db_connection() as conn:
        stamp=integrity._iso(NOW)
        conn.execute("INSERT INTO account_link_decisions(user_id_low,user_id_high,state,risk_score,"
                     "categories_json,reasons_json,input_fingerprint,recompute_id,rule_version,created_at,updated_at)"
                     " VALUES (3,4,'confirmed',100,'[]','[]','test','test','test',?,?)",(stamp,stamp))
        conn.commit()
    result=award(ids=(3,4),win=0)
    assert result['awarded'][0]['amount']==0
    reason,delta=_latest_reason(3)
    assert delta==0
    assert '关联账号' in reason
    assert '基础' not in reason
