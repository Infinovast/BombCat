"""
炸弹猫游戏卡牌库

新增卡牌步骤：
   a. 创建继承自Card的子类
   b. 在Deck._initialize_cards中添加卡牌数量
   c. 在新的"...Card"类中重写use方法处理卡牌效果
"""
import tkinter as tk


CARD_INITIAL_SCORES = {
    "BombCat": -100,
    "Defuse": 100,
    "Nope": 32,
    "Attack": 35,
    "PersonalAttack": 20,
    "Skip": 30,
    "SuperSkip": 50,
    "Shuffle": 22,
    "Swap": 18,
    "DrawBottom": 26,
    "SeeFuture": {3: 24, 5: 30},
    "AlterFuture": {3: 28, 5: 36},
}


def get_card_initial_score(card_key, depth=None):
    score = CARD_INITIAL_SCORES.get(card_key, 0)
    if isinstance(score, dict):
        if depth in score:
            return score[depth]
        return next(iter(score.values())) if score else 0
    return score

class Card:
    """卡牌基类"""

    def __init__(self, name, description, initial_score=0):
        self.name = name
        self.description = description
        self.initial_score = initial_score

    def use(self, game, player, target):
        """使用卡牌效果，需在子类实现"""
        raise NotImplementedError("必须实现use方法")


class BombCatCard(Card):
    """炸弹猫卡"""

    def __init__(self):
        super().__init__("💣炸弹猫", "抽到时必须立即拆除，否则死亡", initial_score=get_card_initial_score("BombCat"))

    def use(self, game, player, target):
        # 实际处理逻辑在抽牌阶段实现
        pass

class DefuseCard(Card):
    """拆除卡"""

    def __init__(self):
        super().__init__("🛠拆除", "拆除炸弹猫并放回牌堆某处", initial_score=get_card_initial_score("Defuse"))

    def use(self, game, player, target):
        # 实际处理逻辑在抽牌阶段实现
        pass

class NopeCard(Card):
    """拒绝卡"""

    def __init__(self):
        super().__init__("🚫拒绝", "对手出的下一张牌失效", initial_score=get_card_initial_score("Nope"))

    def use(self, game, player, target):
        if player.is_ai:
            game.gui.print(f"🚫 AI 打出拒绝，玩家 下次出牌将失效", debug=True)
        else:
            game.gui.print(f"🚫 玩家 打出拒绝，AI 下次出牌将失效")
        game.noped = target

class AttackCard(Card):
    """攻击卡"""

    def __init__(self):
        super().__init__("👊攻击", "让对手执行你的所有回合", initial_score=get_card_initial_score("Attack"))

    def use(self, game, player, target):
        game.gui.print(f"🔥 {player.name} 发动攻击！{target.name} 将要连续行动 {game.remaining_turns + 1} 回合")
        # 实际是在当前回合上加1个回合，因为原有回合会在play_card中进入if self.end_turn or self.end_all_turn，在self._end_turn()中减掉
        game.remaining_turns += 2
        game.current_player = target
        game.end_turn = True  # 注意：不能用all_end！攻击是转移回合给对手，而不是清空回合再轮到对手

class PersonalAttackCard(Card):
    """自我攻击卡"""

    def __init__(self):
        super().__init__("👋自我攻击", "让自己增加2个回合", initial_score=get_card_initial_score("PersonalAttack"))

    def use(self, game, player, target):
        game.gui.print(f"🔥 {player.name} 发动自我攻击，将连续行动 {game.remaining_turns + 2} 回合")
        # 实际上就是在当前回合上加2个回合，因为没有end_turn进不去self._end_turn()
        game.remaining_turns += 2

class SkipCard(Card):
    """跳过卡"""

    def __init__(self):
        super().__init__("⏭️跳过", "跳过当前回合的抽牌阶段", initial_score=get_card_initial_score("Skip"))

    def use(self, game, player, target):
        game.gui.print(f"⏭️ {player.name} 跳过了回合")
        game.end_turn = True

class SuperSkipCard(Card):
    """超级跳过卡"""

    def __init__(self):
        super().__init__("🚀超级跳过", "跳过剩余所有回合的抽牌阶段", initial_score=get_card_initial_score("SuperSkip"))

    def use(self, game, player, target):
        game.gui.print(f"🚀 {player.name} 跳过了剩余所有回合")
        game.end_turn = True
        game.end_all_turn = True

class ShuffleCard(Card):
    """洗牌卡"""

    def __init__(self):
        super().__init__("🔀洗牌", "重新洗牌整个牌堆", initial_score=get_card_initial_score("Shuffle"))

    def use(self, game, player, target):
        game.gui.print("🔀 牌堆被重新洗牌！")
        game.deck.shuffle()
        game.ai_on_shuffle()

class SwapCard(Card):
    """顶底互换卡"""

    def __init__(self):
        super().__init__("🔄顶底互换", "交换牌堆顶部和底部的牌", initial_score=get_card_initial_score("Swap"))

    def use(self, game, player, target):
        if len(game.deck.cards) > 1:
            game.gui.print(f"🔄 {player.name} 交换了牌堆顶部和底部的牌")
            game.deck.cards[0], game.deck.cards[-1] = game.deck.cards[-1], game.deck.cards[0]
            game.ai_on_swap_top_bottom()
        else:
            game.gui.print("😔 牌堆中牌不足，无法进行顶底互换")

class DrawBottomCard(Card):
    """抽底卡"""

    def __init__(self):
        super().__init__("👇抽底", "抽取牌堆底部的牌而不是顶部", initial_score=get_card_initial_score("DrawBottom"))

    def use(self, game, player, target):
        game.gui.print(f"👇 {player.name} 从牌堆底部抽牌")
        game.draw_card(player, from_bottom=True)  # draw_card 会自动结束回合 和 记录ai_known

class SeeFutureCard(Card):
    """预见未来卡"""

    def __init__(self, depth=3):
        super().__init__(
            f"👁预见未来{'-' + str(depth) if depth == 5 else ''}",
            f"查看牌堆顶的{depth}张牌",
            initial_score=get_card_initial_score("SeeFuture", depth=depth),
        )
        self.depth = depth

    def use(self, game, player, target):
        top_count = min(len(game.deck.cards), self.depth)
        if top_count == 0:
            game.gui.print(f"😮 牌堆里没有牌了！")
            return

        top_cards = list(reversed(game.deck.cards[-top_count:]))  # 获取顶部的牌
        game.gui.print(f"🔮 {player.name} 查看了牌堆顶的{top_count}张牌")

        # AI：记录这 top_count 张牌的实例
        if player.is_ai:
            game.ai_on_see_future(top_cards)
            game.gui.print(f"🤖 AI 记录了牌堆顶{top_count}张牌的信息")
            if game.gui.debug_mode:
                game.gui.print("🔽 AI 看到的牌堆顶（从上到下）:", debug=True)
                for i, card in enumerate(top_cards):
                    game.gui.print(f"{i + 1}. {card.name}", debug=True)
        # 玩家
        else:
            cards_info = [f"{i + 1}. {card.name}" for i, card in enumerate(top_cards)]
            game.gui.print("🔽 牌堆顶的牌（从上到下）:")
            for info in cards_info:
                game.gui.print(info)

class AlterFutureCard(Card):
    """改变未来卡"""

    def __init__(self, depth=3):
        super().__init__(
            f"🔄改变未来{'-' + str(depth) if depth == 5 else ''}",
            f"查看并排序牌堆顶的{depth}张牌",
            initial_score=get_card_initial_score("AlterFuture", depth=depth),
        )
        self.depth = depth

    # noinspection SpellCheckingInspection
    def use(self, game, player, target):
        top_count = min(len(game.deck.cards), self.depth)  # 实际上看几张牌
        top_cards = list(reversed(game.deck.cards[-top_count:]))  # 反转顺序
        game.deck.cards = game.deck.cards[:-top_count]  # 移除这些牌
        game.ai_on_remove_top(top_count)

        game.gui.print(f"🔄 {player.name} 正在重新排列牌堆顶的{top_count}张牌")

        # AI逻辑：将爆炸猫（如果有）放在第2张位置给玩家
        if player.is_ai:
            before_cards = list(reversed(top_cards))
            # 统一在“从上到下”的抽牌顺序视角下排序和放置。
            draw_order = list(reversed(top_cards))  # 顶 -> 底
            non_bomb_cards = [c for c in draw_order if not isinstance(c, BombCatCard)]
            bomb_cards = [c for c in draw_order if isinstance(c, BombCatCard)]

            # 其余卡牌按分值排序，高分优先放在更早抽到的位置。
            non_bomb_cards.sort(key=lambda c: getattr(c, "initial_score", 0), reverse=True)

            if bomb_cards:
                if game.remaining_turns == 1 and non_bomb_cards:
                    # AI 本回合只会再抽1张：把炸弹放到第2张，优先转移给玩家。
                    draw_order = [non_bomb_cards[0], bomb_cards[0], *non_bomb_cards[1:]]
                    # 额外炸弹继续后置。
                    draw_order.extend(bomb_cards[1:])
                else:
                    # AI 仍可能连续行动时，把炸弹后置。
                    draw_order = non_bomb_cards + bomb_cards
            else:
                draw_order = non_bomb_cards

            # 转回当前逻辑内部使用顺序。
            top_cards = list(reversed(draw_order))
            game.gui.print("🤖 AI 重新排列了牌堆顶的牌")

            if game.gui.debug_mode:
                game.gui.print("🔽 AI 改变未来前（从上到下）:", debug=True)
                for i, card in enumerate(reversed(before_cards)):
                    game.gui.print(f"{i + 1}. {card.name}", debug=True)
                game.gui.print("🔽 AI 改变未来后（从上到下）:", debug=True)
                for i, card in enumerate(draw_order):
                    game.gui.print(f"{i + 1}. {card.name}", debug=True)

            # 将排序后的牌放回牌堆
            for card in top_cards:  # 倒序添加以保持原先的顺序
                game.deck.cards.append(card)
            game.ai_on_append_known(top_cards)

        # 玩家逻辑：用点击界面让玩家重新排序卡牌
        else:
            # 创建卡牌选择对话框
            dialog = tk.Toplevel(game.gui.root)
            dialog.title("重新排序卡牌")
            dialog.geometry(f"300x{300 if self.depth == 3 else 400}")  # 根据看3张还是5张决定菜单高度
            dialog.transient(game.gui.root)
            dialog.grab_set()

            # 在主窗口上居中显示对话框
            x = game.gui.root.winfo_x() + game.gui.root.winfo_width() // 2 - 200
            y = game.gui.root.winfo_y() + game.gui.root.winfo_height() // 2 - 150
            dialog.geometry(f"+{x}+{y}")

            tk.Label(dialog, text="🔄 点击两张卡牌互换其位置（顺序为从上到下）：").pack(pady=10)

            # 创建卡牌框架
            cards_frame = tk.Frame(dialog)
            cards_frame.grid_columnconfigure(0, weight=1)
            cards_frame.pack(fill="both", expand=True, padx=20, pady=10)

            # 卡牌按钮和顺序
            card_btns = []
            selected_index = [None]  # 使用列表存储选中的索引，便于在函数间共享

            # 更新卡牌显示顺序
            def update_card_display():
                for i, _btn in enumerate(card_btns):
                    _btn.config(text=f"{i + 1}. {top_cards[i].name}")
                    _btn.grid(row=i, column=0, sticky="ew", pady=2)

            # 点击卡牌处理
            def on_card_click(index):
                first_idx = selected_index[0] if selected_index[0] is not None else index
                if selected_index[0] is None:
                    # 选择第一张卡
                    selected_index[0] = index
                    card_btns[index].config(bg="lightblue")
                else:
                    # 交换两张卡
                    top_cards[first_idx], top_cards[index] = top_cards[index], top_cards[first_idx]
                    card_btns[first_idx].config(bg="SystemButtonFace")
                    selected_index[0] = None
                    update_card_display()

            # 创建卡牌按钮
            for i in range(top_count):
                btn = tk.Button(cards_frame,
                                text=f"{i + 1}. {top_cards[i].name}",
                                width=30, height=2,
                                anchor="center", justify="center",
                                command=lambda idx=i: on_card_click(idx))
                btn.grid(row=i, column=0, sticky="ew", pady=2)
                card_btns.append(btn)

            result_var = tk.BooleanVar(value=False)

            def on_confirm():
                result_var.set(True)
                dialog.destroy()

            def on_cancel():
                # 恢复原始顺序
                top_cards[:] = list(reversed(game.deck.cards[-top_count:]))
                dialog.destroy()

            # 按钮框架
            btn_frame = tk.Frame(dialog)
            btn_frame.pack(fill="x", pady=10)

            tk.Button(btn_frame, text="确认", command=on_confirm).pack(side="left", padx=20, expand=True)
            tk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right", padx=20, expand=True)

            # 等待对话框关闭
            dialog.wait_window()

            # 显示最终顺序
            if result_var.get():
                game.gui.print("🔽 现在牌堆顶的牌（从上到下）:")
                for i, card in enumerate(top_cards):
                    game.gui.print(f"{i + 1}. {card.name}")

            # 将排序后的牌放回牌堆
            for card in reversed(top_cards):
                game.deck.cards.append(card)

            # 更新 AI 认知：玩家确认后会公开顺序日志，AI应同步为已知。
            if result_var.get():
                game.ai_on_append_known(top_cards)
            else:
                game.ai_on_append_unknown(top_count)

if __name__ == "__main__":
    import BombCatGUI
    BombCatGUI.main()
