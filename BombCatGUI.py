"""
BombCatGUI
爆炸猫游戏的图形界面实现
"""

import tkinter as tk
from tkinter import ttk
import random
from BombCat import *


class Deck:
    """牌堆管理器"""

    def __init__(self):
        self.cards = []
        self.discard_pile = []
        self._initialize_cards()
        self.shuffle()

    def _initialize_cards(self):
        # 卡牌配置区（可在此添加新卡牌）
        cards = [
            *[BombCatCard() for _ in range(3)],  # 炸弹猫
            *[DefuseCard() for _ in range(4)],  # 拆除卡
            *[AttackCard() for _ in range(6)],  # 攻击卡
            *[SkipCard() for _ in range(6)],  # 跳过卡
            *[ShuffleCard() for _ in range(4)],  # 洗牌卡
            *[SeeFutureCard() for _ in range(4)],  # 预见未来卡
            *[AlterFutureCard() for _ in range(4)],  # 改变未来卡
            *[DrawBottomCard() for _ in range(4)],  # 抽底卡
            *[SwapCard() for _ in range(4)],  # 顶底互换卡
        ]
        self.cards = cards

    def shuffle(self):
        """洗牌操作"""
        random.shuffle(self.cards)

    def draw(self, num=1, from_bottom=False, refuse=None):
        """抽牌操作"""
        drawn = []
        for _ in range(num):
            if not self.cards:
                self.refill_from_discard()
            if self.cards:
                if refuse:
                    for card in self.cards if not from_bottom else reversed(self.cards):
                        if not any(isinstance(card, type(r)) for r in refuse):
                            drawn.append(card)
                            self.cards.remove(card)
                            break
                else:
                    drawn.append(self.cards.pop(-1 if not from_bottom else 0))
        return drawn

    def refill_from_discard(self):
        """用弃牌堆补充牌堆"""
        print("♻️ 弃牌堆洗入牌堆")
        self.cards = self.discard_pile.copy()
        self.discard_pile.clear()
        self.shuffle()

    def insert_card(self, card, position):
        """将卡牌插入指定位置"""
        self.cards.insert(position, card)


class Player:
    """玩家类"""

    def __init__(self, name, is_ai=False):
        self.name = name
        self.hand = []
        self.hand_limit = 9  # 设置手牌上限
        self.is_ai = is_ai
        self.alive = True

    def has_defuse(self):
        """检查是否有拆除卡"""
        return any(isinstance(c, DefuseCard) for c in self.hand)

    def get_specific_cards(self, card_type):
        """获取可主动使用的卡牌"""
        if card_type == "playable":
            return [c for c in self.hand if not isinstance(c, (DefuseCard, BombCatCard))]
        elif card_type == "defensive":
            return [c for c in self.hand if isinstance(c, (SkipCard, AttackCard, ShuffleCard, DrawBottomCard, SwapCard, AlterFutureCard))]
        else:
            return [c for c in self.hand if isinstance(c, card_type)] if isinstance(card_type, (type, tuple)) else []


class Game:
    """游戏控制器"""

    def __init__(self, gui=None):
        self.deck = Deck()  # 创建Deck(牌堆)实例
        self.player = Player("玩家")  # 创建Player(玩家)实例
        self.ai = Player("AI", is_ai=True)  # 创建Player(AI)实例
        self.gui = gui  # 保存GUI引用，用于更新界面

        self._init_hands()
        self.remaining_turns = 1
        self.current_player = self.player
        self.waiting_for_input = True
        self.end_turn = False
        self.ai_knows_bomb_on_top = False
        self.game_running = False  # Game初始化的时候游戏未开始，在start_game()中才设置为True

        # 如果有GUI，设置引用
        if gui:
            gui.set_game(self)

    def _init_hands(self):
        """初始化玩家手牌"""
        for p in [self.player, self.ai]:
            # 强制加入一张拆除卡
            defuse = next(c for c in self.deck.cards if isinstance(c, DefuseCard))
            self.deck.cards.remove(defuse)
            p.hand.append(defuse)
            # 抽7张牌
            p.hand.extend(self.deck.draw(7, refuse=[BombCatCard()]))

    def play_card(self, player, card):
        """处理出牌逻辑"""
        if player == self.current_player:
            if card in player.hand:
                target = self.get_other(player)
                self.gui.print(f"🎴 {player.name}使用了 {card.name}")

                card_tmp = card
                player.hand.remove(card)  # 卡牌先消耗再执行效果，针对满牌时用抽底
                card_tmp.use(self, player, target)
                self.deck.discard_pile.append(card)
                self.gui.update_gui()

                if self.end_turn:
                    self.end_turn = False
                    self._end_turn()

                return True
        return False

    def draw_card(self, player, from_bottom=False):
        """处理抽牌逻辑"""
        all_end = False
        if player == self.current_player:
            if len(player.hand) >= player.hand_limit:
                if self.gui:
                    self.gui.print(f"😔 {player.name}手牌已满 ({self.player.hand_limit})，请先出牌！")
                return False

            if drawn := self.deck.draw(1, from_bottom=from_bottom):
                card = drawn[0]
                if isinstance(card, BombCatCard):
                    self._handle_bomb_cat(player, card)
                    all_end = True  # 如果抽到炸弹猫，结束所有回合
                else:
                    player.hand.append(card)
                    if self.gui:
                        if player.is_ai and not self.gui.debug_mode:
                            self.gui.print(f"🤖 AI完成抽牌")
                        else:
                            self.gui.print(f"🃏 {player.name}抽到了 {card.name}")

                if self.gui:
                    self.gui.update_gui()

                self._end_turn(all_end)  # 抽牌后结束回合!
                return True
            else:
                if self.gui:
                    self.gui.print("牌堆已空！")
                return False
        return False

    def _handle_bomb_cat(self, player, bomb_card):
        """处理炸弹猫逻辑"""
        if self.gui:
            self.gui.print(f"💣 {player.name}抽到了炸弹猫！")

        if player.has_defuse():
            if self.gui:
                self.gui.print(f"🛠 {player.name}使用拆除卡...")

            defuse_card = next(c for c in player.hand if isinstance(c, DefuseCard))
            player.hand.remove(defuse_card)
            self.deck.discard_pile.append(defuse_card)

            # 处理放回位置选择
            if player.is_ai:
                pos = random.randint(0, len(self.deck.cards))
                if self.gui:
                    if player.is_ai and not self.gui.debug_mode:
                        self.gui.print(f"🤖 AI将炸弹猫放回牌堆某个位置")
                    else:
                        self.gui.print(f"🤖 AI将炸弹猫放回第 {pos} 位 (0~{len(self.deck.cards)})")
                self.deck.insert_card(bomb_card, pos)
            else:
                # 让GUI处理玩家选择
                if self.gui:
                    position = self.gui.prompt_bomb_position(len(self.deck.cards))
                    if position is not None:
                        self.deck.insert_card(bomb_card, position)
                    else:
                        # 默认放在随机位置
                        pos = random.randint(0, len(self.deck.cards))
                        if self.gui:
                            self.gui.print(f"默认将炸弹猫放回第 {pos} 位 (0~{len(self.deck.cards)})")
                        self.deck.insert_card(bomb_card, pos)

            if self.gui and self.remaining_turns > 1:
                self.gui.print(f"{player.name}剩余的 {self.remaining_turns - 1} 个回合全部结束")

        else:
            if self.gui:
                self.gui.print(f"💥 {player.name}没有拆除卡！爆炸了！")
            player.alive = False
            self.check_game_end()

    def _end_turn(self, all_end=False):
        """结束回合处理"""
        if all_end:  # 如果抽到炸弹猫，结束所有回合
            self.remaining_turns = 1
            self.current_player = self.get_other(self.current_player)
        elif self.remaining_turns > 0:
            self.remaining_turns -= 1
            if self.remaining_turns == 0:
                self.remaining_turns = 1
                self.current_player = self.get_other(self.current_player)

        if self.ai.alive and self.player.alive and self.gui:
            if self.current_player.is_ai:
                self.gui.schedule_ai_turn()
            else:
                self.gui.print("\n────────── 🎉 玩家回合 ──────────")

        self.check_game_end()
        if self.gui:
            self.gui.update_gui()

    def check_game_end(self):
        """检查游戏是否结束"""
        if not self.player.alive or not self.ai.alive:
            if self.gui:
                self.gui.game_end()
                self.game_running = False
            return True
        return False

    def run_ai_turn(self):
        """执行AI回合"""
        if self.current_player != self.ai or not self.ai.alive:
            return

        if self.gui:
            self.gui.print("\n────────── 🤖 AI回合 ──────────\n🤖 AI正在思考...")

        # AI决策逻辑
        while self.current_player == self.ai and self.ai.alive:
            # 检查是否知道顶牌是炸弹猫
            if self.ai_knows_bomb_on_top:
                cards = self.ai.get_specific_cards('defensive')
                action = 'play' if cards else 'draw'
                self.ai_knows_bomb_on_top = False
            elif len(self.ai.hand) >= self.ai.hand_limit:
                cards = self.ai.get_specific_cards('playable')
                action = 'play'
            else:
                # AI随机选择行动
                cards = self.ai.get_specific_cards('playable')
                action = random.choice(['play', 'draw']) if cards and len(self.ai.hand) < self.ai.hand_limit else 'draw'

            if action == 'play' and cards:
                card = random.choice(cards)
                self.play_card(self.ai, card)
                if self.end_turn:
                    break
            else:
                if self.gui:
                    self.gui.print("🤖 AI选择抽牌")
                self.draw_card(self.ai)
                break

        if self.gui:
            self.gui.update_gui()

    def get_other(self, player):
        """获取对手实例"""
        return self.ai if player == self.player else self.player


class GUI:
    """图形用户界面类"""

    def __init__(self, root, debug_mode=False):
        # 设置窗口属性
        self.root = root
        self.root.title("BombCat-GUI")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        # 界面变量
        self.player_cards_var = None
        self.ai_cards_var = None
        self.player_cards = None

        # UI组件
        self.turn_label = None
        self.deck_label = None
        self.mode_label = None
        self.player_status = None
        self.ai_status = None
        self.log_text = None

        # 按钮
        self.start_button = None
        self.quit_button = None
        self.draw_button = None
        self.play_button = None

        # 初始化窗口
        self.init_window()

        # 游戏引用
        self.debug_mode = debug_mode
        self.game = Game(gui=self)

    def set_game(self, game):
        """设置游戏引用"""
        self.game = game
        self.update_gui()

    def print(self, message, debug=False):
        """输出到日志栏"""
        # 如果不是调试模式，则不输出调试信息
        if debug and not self.debug_mode:
            return

        # 如果开启了调试模式，则同时使用print输出
        if self.debug_mode:
            print(message)

        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.config(state="normal")
            self.log_text.tag_configure("center", justify="center")  # 定义居中标签
            self.log_text.insert("end", message + "\n", "center")  # 应用居中标签
            self.log_text.see("end")
            self.log_text.config(state="disabled")

    def start_game(self):
        """启动新游戏/重新启动游戏"""
        if self.game.game_running:
            if messagebox.askyesno("确认", "游戏正在进行，是否重新开始？"):
                self.game = Game(gui=self)  # 初始化，但不重新创建GUI
            else:
                return
        elif not self.game.ai.alive or not self.game.player.alive:
            self.game = Game(gui=self)

        self.game.game_running = True  # 游戏这时才开始

        # 清空日志
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

        # 启用玩家操作按钮
        self.draw_button.config(state=tk.NORMAL)
        self.play_button.config(state=tk.NORMAL)
        # self.start_button.config(state=tk.DISABLED)

        # 更新界面
        self.print("[🐱 BombCat 爆炸猫]\n游戏开始！\n\n────────── 🎉 玩家回合 ──────────")
        self.update_gui()

    def update_gui(self):
        """更新所有显示"""
        if not self.game:
            return

        # 更新玩家手牌
        hand_text = ""
        for idx, card in enumerate(self.game.player.hand):
            hand_text += f"{idx + 1}. {card.name}  "
        self.player_cards_var.set(hand_text)

        # 更新AI手牌数量
        self.ai_cards_var.set(f"数量: {len(self.game.ai.hand)}张")

        # 更新游戏状态区的标签
        current = "玩家" if self.game.current_player == self.game.player else "AI"
        self.turn_label.config(text=f"当前回合: {current} (剩余{self.game.remaining_turns}回合)")
        self.deck_label.config(text=f"牌堆剩余: {len(self.game.deck.cards)}张")
        self.mode_label.config(text=f"游戏模式: {'Debug' if self.debug_mode else '正常'}")
        player_status = "存活" if self.game.player.alive else "死亡"
        ai_status = "存活" if self.game.ai.alive else "死亡"

        self.player_status.config(text=f"玩家状态: {player_status}")
        self.ai_status.config(text=f"AI状态: {ai_status}")

        self.root.update()

    def init_window(self):
        """创建并初始化GUI窗口"""
        # 创建主窗口框架
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill="both", expand=True)

        # 状态区域
        status = ttk.LabelFrame(main, text="游戏状态", padding="5")
        status.pack(fill="x", pady=5)
        labels = [("turn_label", "当前回合: 未开始"), ("deck_label", "牌堆剩余: 0"),
                  ("player_status", "玩家状态: 存活"), ("ai_status", "AI状态: 存活"),
                  ("mode_label", "游戏模式: 正常")
                  ]
        for i, (attr, text) in enumerate(labels):
            setattr(self, attr, ttk.Label(status, text=text))
            getattr(self, attr).grid(row=0, column=i, padx=10, sticky="w")

        # 日志区域
        log_frame = ttk.LabelFrame(main, text="游戏日志", padding="5")
        log_frame.pack(fill="both", expand=True, pady=5)
        self.log_text = tk.Text(log_frame, height=10, width=80, wrap="word", font=("Microsoft YaHei", 11))
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set, state="disabled")

        # 手牌区域
        hands = ttk.Frame(main)
        hands.pack(fill="x", pady=5)

        # 玩家和AI手牌
        for side, name, is_player in [("left", "玩家", True), ("right", "AI", False)]:
            frame = ttk.LabelFrame(hands, text=f"{name}手牌", padding="5")
            frame.pack(side=side, fill="both", expand=True)

            var_name = f"{'player' if is_player else 'ai'}_cards_var"
            setattr(self, var_name, tk.StringVar())
            label = ttk.Label(frame, textvariable=getattr(self, var_name))
            if is_player:
                self.player_cards = label
                label.configure(wraplength=600)
            label.pack(fill="both", expand=True)

        # 按钮区域
        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=5)

        button_sections = [
            ("left", "游戏控制", [("start_button", "开始游戏", self.start_game, {}),
                              ("quit_button", "退出游戏", self.quit_game, {})]),
            ("right", "玩家操作", [("draw_button", "抽牌", self.handle_player_draw, {"state": "disabled"}),
                               ("play_button", "出牌", self.handle_player_play, {"state": "disabled"})]),
        ]

        for side, title, buttons in button_sections:
            frame = ttk.LabelFrame(actions, text=title, padding="5")
            frame.pack(side=side, fill="x", expand=True, anchor="w")
            for attr, text, cmd, opts in buttons:
                btn = ttk.Button(frame, text=text, command=cmd, **opts)
                setattr(self, attr, btn)
                btn.pack(side="left", padx=5)

    def handle_player_draw(self):
        """处理玩家抽牌"""
        if not self.game:
            return

        if self.game.current_player != self.game.player:
            messagebox.showinfo("提示", "现在不是你的回合！")
            return

        if len(self.game.player.hand) >= self.game.player.hand_limit:
            messagebox.showinfo("提示", f"😔 手牌已满 ({self.game.player.hand_limit})，请先出牌！")
            return

        self.game.draw_card(self.game.player)

    def handle_player_play(self):
        """处理玩家出牌"""
        if not self.game:
            return

        if self.game.current_player != self.game.player:
            messagebox.showinfo("提示", "现在不是你的回合！")
            return

        player = self.game.player
        cards = player.get_specific_cards('playable')
        if not cards:
            messagebox.showinfo("提示", "没有可用的卡牌")
            return

        # 创建卡牌选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("选择卡牌")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中显示对话框
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f'+{x}+{y}')

        # 创建卡牌列表
        tk.Label(dialog, text="选择要使用的卡牌:").pack(pady=10)
        card_list = tk.Listbox(dialog, height=10, width=50)
        card_list.pack(fill="both", expand=True, padx=10, pady=5)

        for i, card in enumerate(cards):
            card_list.insert(tk.END, f"{i + 1}. {getattr(card, 'name', '未知卡牌')}: {getattr(card, 'description', '无描述')}")

        def use_selected_card():
            """使用选中的卡牌"""
            selection = card_list.curselection()
            if not selection:
                messagebox.showinfo("提示", "请先选择一张卡牌")
                return

            index = selection[0]
            card = cards[index]
            dialog.destroy()

            # 调用游戏逻辑处理出牌
            self.game.play_card(player, card)

        # 绑定双击事件
        card_list.bind('<Double-1>', lambda e: use_selected_card())

        # 添加按钮
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill="x", pady=10)
        tk.Button(btn_frame, text="确认", command=use_selected_card).pack(side="left", padx=10, expand=True)
        tk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side="right", padx=10, expand=True)

    def prompt_bomb_position(self, max_pos):
        """提示玩家选择炸弹猫放回位置"""
        position = simpledialog.askinteger("选择位置",
                                          f"将炸弹猫放回的位置 (底部 0-顶部 {max_pos})：",
                                          minvalue=0, maxvalue=max_pos)
        if position is not None:
            self.print(f"🐱 将炸弹猫放回第 {position} 位")
        return position

    def schedule_ai_turn(self):
        """安排AI回合"""
        self.root.after(1000, self.game.run_ai_turn)  # 延迟1秒后执行AI回合

    def game_end(self):
        """游戏结束处理"""
        if not self.game or self.game.game_running:
            return

        self.print("\n────────── 🎮 游戏结束 ──────────")

        if self.game.player.alive and not self.game.ai.alive:
            self.print("🎉 恭喜！玩家获胜！")
            messagebox.showinfo("游戏结束", "你赢了！")
        elif self.game.ai.alive and not self.game.player.alive:
            self.print("😢 AI获胜！")
            messagebox.showinfo("游戏结束", "AI赢了！")
        else:
            self.print("😐 平局！")
            messagebox.showinfo("游戏结束", "平局！")

        self.print("🎉 感谢游玩！按[开始游戏]重新开始或[退出游戏]退出...")

        # 禁用游戏操作按钮
        self.draw_button.config(state=tk.DISABLED)
        self.play_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)

    def quit_game(self):
        """退出游戏"""
        if messagebox.askyesno("确认", "确定要退出游戏吗？"):
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = GUI(root, debug_mode=False)
    root.mainloop()
