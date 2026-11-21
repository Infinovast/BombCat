"""卡牌展示数据与原始 Tkinter 排序弹窗；规则结算位于 game_core.py。"""
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
        return game.play_card(player, self)


class BombCatCard(Card):
    """炸弹猫卡"""

    def __init__(self):
        super().__init__("💣炸弹猫", "抽到时必须立即拆除，否则死亡", initial_score=get_card_initial_score("BombCat"))


class DefuseCard(Card):
    """拆除卡"""

    def __init__(self):
        super().__init__("🛠拆除", "拆除炸弹猫并放回牌堆某处", initial_score=get_card_initial_score("Defuse"))


class NopeCard(Card):
    """拒绝卡"""

    def __init__(self):
        super().__init__("🚫拒绝", "对手出的下一张牌失效", initial_score=get_card_initial_score("Nope"))


class AttackCard(Card):
    """攻击卡"""

    def __init__(self):
        super().__init__("👊攻击", "让对手执行你的所有回合", initial_score=get_card_initial_score("Attack"))


class PersonalAttackCard(Card):
    """自我攻击卡"""

    def __init__(self):
        super().__init__("👋自我攻击", "让自己增加2个回合", initial_score=get_card_initial_score("PersonalAttack"))


class SkipCard(Card):
    """跳过卡"""

    def __init__(self):
        super().__init__("⏭️跳过", "跳过当前回合的抽牌阶段", initial_score=get_card_initial_score("Skip"))


class SuperSkipCard(Card):
    """超级跳过卡"""

    def __init__(self):
        super().__init__("🚀超级跳过", "跳过剩余所有回合的抽牌阶段", initial_score=get_card_initial_score("SuperSkip"))


class ShuffleCard(Card):
    """洗牌卡"""

    def __init__(self):
        super().__init__("🔀洗牌", "重新洗牌整个牌堆", initial_score=get_card_initial_score("Shuffle"))


class SwapCard(Card):
    """顶底互换卡"""

    def __init__(self):
        super().__init__("🔄顶底互换", "交换牌堆顶部和底部的牌", initial_score=get_card_initial_score("Swap"))


class DrawBottomCard(Card):
    """抽底卡"""

    def __init__(self):
        super().__init__("👇抽底", "抽取牌堆底部的牌而不是顶部", initial_score=get_card_initial_score("DrawBottom"))


class SeeFutureCard(Card):
    """预见未来卡"""

    def __init__(self, depth=3):
        super().__init__(
            f"👁预见未来{'-' + str(depth) if depth == 5 else ''}",
            f"查看牌堆顶的{depth}张牌",
            initial_score=get_card_initial_score("SeeFuture", depth=depth),
        )
        self.depth = depth


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

def prompt_card_order(game, depth, cards):
    """Present the original ordering dialog and return the chosen top-first order."""
    top_cards = list(cards)
    original_cards = top_cards.copy()
    top_count = len(top_cards)
    # 创建卡牌选择对话框
    dialog = tk.Toplevel(game.gui.root)
    dialog.title("重新排序卡牌")
    dialog.geometry(f"300x{300 if depth == 3 else 400}")  # 根据看3张还是5张决定菜单高度
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
        top_cards[:] = original_cards
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    # 按钮框架
    btn_frame = tk.Frame(dialog)
    btn_frame.pack(fill="x", pady=10)

    tk.Button(btn_frame, text="确认", command=on_confirm).pack(side="left", padx=20, expand=True)
    tk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right", padx=20, expand=True)

    # 等待对话框关闭
    dialog.wait_window()
    if game.gui.game is not game or not game.game_running:
        return

    # 显示最终顺序
    if result_var.get():
        game.gui.print("🔽 现在牌堆顶的牌（从上到下）:")
        for i, card in enumerate(top_cards):
            game.gui.print(f"{i + 1}. {card.name}")


    return top_cards
