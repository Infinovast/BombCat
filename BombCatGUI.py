"""
BombCatGUI
爆炸猫游戏的图形界面实现
"""
import random
from ctypes import windll
from tkinter import ttk, messagebox, simpledialog
from typing import Literal

from BombCat import *


class Deck:
    """牌堆管理器"""

    def __init__(self):
        self.cards = []
        self.discard_pile = []
        self.amounts = {BombCatCard: 4, DefuseCard: 4, NopeCard: 3, AttackCard: 4, SkipCard: 3, SuperSkipCard: 2,
                        ShuffleCard: 2, SeeFutureCard: 2, AlterFutureCard: 3, DrawBottomCard: 2, SwapCard: 2
        }
        self._initialize_cards()
        self.shuffle()

    def _initialize_cards(self):
        # 卡牌配置区（可在此添加新卡牌）
        cards = [
            *[BombCatCard() for _ in range(self.amounts[BombCatCard])],  # 炸弹猫
            *[DefuseCard() for _ in range(self.amounts[DefuseCard])],  # 拆除卡
            *[NopeCard() for _ in range(self.amounts[DefuseCard])],  # 拒绝卡
            *[AttackCard() for _ in range(self.amounts[AttackCard])],  # 攻击卡
            *[SkipCard() for _ in range(self.amounts[SkipCard])],  # 跳过卡
            *[SuperSkipCard() for _ in range(self.amounts[SkipCard])],  # 超级跳过卡
            *[ShuffleCard() for _ in range(self.amounts[ShuffleCard])],  # 洗牌卡
            *[SeeFutureCard() for _ in range(self.amounts[SeeFutureCard])],  # 预见未来卡
            *[AlterFutureCard() for _ in range(self.amounts[AlterFutureCard])],  # 改变未来卡
            *[DrawBottomCard() for _ in range(self.amounts[DrawBottomCard])],  # 抽底卡
            *[SwapCard() for _ in range(self.amounts[SwapCard])],  # 顶底互换卡
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
        """获取手牌中指定卡牌"""
        if card_type == "playable":
            return [c for c in self.hand if not isinstance(c, (DefuseCard, BombCatCard))]
        elif card_type == "defensive":
            return [c for c in self.hand if isinstance(c, (SkipCard, AttackCard, ShuffleCard, DrawBottomCard, SwapCard, AlterFutureCard))]
        elif card_type == "escape":
            return [c for c in self.hand if isinstance(c, (SkipCard, SuperSkipCard, AttackCard))]
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
        self.all_end = False
        self.game_running = False  # Game初始化的时候游戏未开始，在start_game()中才设置为True
        self.ai_known = ["unknown"] * len(self.deck.cards)  # AI 对牌堆每张牌的认知：Card 实例 或 "unknown"
        self.noped = None  # =None 无人被Nope | self.player 对玩家生效 | self.ai 对AI生效

        # 如果有GUI，设置引用
        if gui:
            gui.set_game(self)

    def _init_hands(self):
        """初始化双方手牌"""
        for p in [self.player, self.ai]:
            p.hand.append(DefuseCard())  # 强制加入一张拆除卡
            p.hand.extend(self.deck.draw(5, refuse=[BombCatCard()]))  # 再抽5张牌

    def ai_control(self):
        """
        基于 ai_known 决策 AI 行为: 1. 抢拆除卡 2. 避开已知炸弹
        Returns:
            tuple: 返回值格式为 ('play', [可用卡牌]) 或 ('draw', None)
        """
        # 已知的炸弹和拆除卡在牌堆中的位置
        bomb_pos = [i for i, c in enumerate(self.ai_known) if isinstance(c, BombCatCard)]
        defuse_pos = [i for i, c in enumerate(self.ai_known) if isinstance(c, DefuseCard)]
        top_idx = len(self.ai_known) - 1
        bottom_idx = 0

        # 获取手牌中各种卡
        next_cards = self.ai.get_specific_cards('escape')
        ssk = self.ai.get_specific_cards(SuperSkipCard)
        sw = self.ai.get_specific_cards(SwapCard)
        sh = self.ai.get_specific_cards(ShuffleCard)
        db = self.ai.get_specific_cards(DrawBottomCard)

        # 若已知炸弹猫位置，进攻玩家或绕过
        if bomb_pos:
            # 炸弹猫在顶
            if bomb_pos[-1] == top_idx:
                # 有逃跑牌（跳过/攻击/抽底）则使用
                if self.remaining_turns > 1 and ssk:
                    return 'play', ssk
                if next_cards:
                    return 'play', random.choice(next_cards)
                # 否则尝试交换或洗牌
                if sw:
                    return 'play', sw
                if sh:
                    return 'play', sh

            # 如果炸弹猫在第2张且下回合是玩家，直接抽走第1张
            if bomb_pos[-1] == top_idx - 1 and self.remaining_turns == 1:
                if len(self.ai.hand) < self.ai.hand_limit:
                    return 'draw', None

            # 如果炸弹猫在底部且有进攻牌，尝试用顶底互换然后下次进函数时跳过自己
            if bomb_pos[0] == bottom_idx and sw and next_cards:
                return 'play', sw

        # 若已知拆除卡位置，手中无拆除卡则必抢牌，否则随机
        if defuse_pos and (not self.ai.has_defuse() or random.random() < 0.8):
            # 拆除卡在顶，直接抽牌
            if defuse_pos[-1] == top_idx:
                if len(self.ai.hand) < self.ai.hand_limit:
                    return 'draw', None
            # 拆除卡在底，优先出“抽底卡”再抽
            if defuse_pos[0] == bottom_idx:
                if db:
                    return 'play', db
                if sw:
                    return 'play', sw
            # 否则尝试用“顶底互换”将目标拉到可抽位置
            if sw:
                return 'play', sw
            # 最后才抽牌
            if len(self.ai.hand) < self.ai.hand_limit:
                return 'draw', None

        # 常规逻辑：手牌满时优先出牌，否则随机
        cards = self.ai.get_specific_cards('playable')
        if len(self.ai.hand) >= self.ai.hand_limit:
            return 'play', random.choice(cards)
        if cards:
            return random.choice([('play', cards), ('draw', None)])
        return 'draw', None

    def run_ai_turn(self):
        """执行AI回合"""
        if not self.current_player.is_ai or not self.ai.alive:
            return

        # AI决策逻辑
        while self.current_player.is_ai and self.ai.alive:
            # 统一由 control_ai 决定
            action, _card = self.ai_control()
            if action == 'play' and _card:
                self.play_card(self.ai, _card)
                if self.end_turn:
                    break
            else:
                if self.gui:
                    self.gui.print("🖐 AI 选择抽牌")
                self.draw_card(self.ai)
                break

        if self.gui:
            self.gui.update_gui()

    def play_card(self, player, _card):
        """处理双方出牌的底层函数"""
        # 传入的_card可能是单个卡牌，也可能是全为同种卡牌的列表，所以这里要处理
        if isinstance(_card, list):
            card = _card[0]  # 只出一张，且_card列表里面每个元素都一样
        else:
            card = _card  # 这个时候_card就是单个卡牌

        if self.noped == player:  # 处理打出来的牌被Nope的情况
            self.noped = None
            self.gui.print(f"🚫 {player.name} 打出的 {card.name} 被 {self.get_other(player).name} 的拒绝卡阻止")
            # 被Nope的牌也要消耗
            player.hand.remove(card)
            self.deck.discard_pile.append(card)
            self.gui.update_gui()
            return False

        self.all_end = False
        if (player == self.current_player or card is NopeCard) and card in player.hand:
            if isinstance(card, NopeCard):  # 特别处理Nope卡
                if self.noped == self.get_other(player):
                    if not player.is_ai:
                        self.gui.print(f"❌ 已存在 玩家 打出的拒绝卡，请勿重复打出")
                    return False
            else:
                self.gui.print(f"🎴 {player.name} 使用了 {card.name}")

            target = self.get_other(player)
            player.hand.remove(card)  # 卡牌先消耗再执行效果，针对满牌时用抽底
            card.use(self, player, target)
            self.deck.discard_pile.append(card)
            self.gui.update_gui()

            if self.end_turn or self.all_end:
                self.end_turn = False
                self._end_turn()
            elif not (isinstance(card, NopeCard) and player.is_ai):
                # 间隔下一部分出牌/抽牌文字（同属一个player）
                # 抽牌/end_turn/all_end为True不需要间隔，因为一定结束回合，下面有回合分界线
                self.gui.print("───────/───────")
            return True

        return False

    def draw_card(self, player, from_bottom=False):
        """处理双方抽牌的底层函数"""
        self.all_end = False
        if player == self.current_player:
            if len(player.hand) >= player.hand_limit:
                if self.gui:
                    self.gui.print(f"🈵 {player.name}手牌已满 (上限为{self.player.hand_limit}张)，请先出牌！")
                return False

            # 这里从牌堆中抽得drawn
            if drawn := self.deck.draw(1, from_bottom=from_bottom):
                # 同步移除ai_known中对应位置
                if from_bottom:
                    self.ai_known.pop(0)
                else:
                    self.ai_known.pop(-1)

                card = drawn[0]
                if isinstance(card, BombCatCard):
                    self._handle_bomb_cat(player, card)
                    self.all_end = True  # 如果抽到炸弹猫，结束所有回合
                else:
                    player.hand.append(card)
                    if self.gui:
                        if player.is_ai and not self.gui.debug_mode:
                            self.gui.print(f"🤖 AI 完成抽牌")
                        else:
                            self.gui.print(f"🖐 {player.name} 抽到了 {card.name}")

                if self.gui:
                    self.gui.update_gui()

                self._end_turn()  # 抽牌后一定结束回合
                return True
            else:
                if self.gui:
                    self.gui.print("牌堆已空！")
                return False
        return False

    def _handle_bomb_cat(self, player, bomb_card):
        """处理炸弹猫逻辑"""
        if self.gui:
            self.gui.print(f"💣 {player.name} 抽到了炸弹猫！")

        # 不能用use，否则会被Nope拦截
        if player.has_defuse():
            if self.gui:
                self.gui.print(f"🛠 {player.name} 使用拆除卡...")

            defuse_card = next(c for c in player.hand if isinstance(c, DefuseCard))
            player.hand.remove(defuse_card)
            self.deck.discard_pile.append(defuse_card)

            # 处理放回位置选择
            if player.is_ai:
                pos = random.randint(0, len(self.deck.cards))
                if self.gui:
                    if player.is_ai and not self.gui.debug_mode:
                        self.gui.print(f"🤖 AI 将炸弹猫放回牌堆某个位置")
                    else:
                        self.gui.print(f"🤖 AI 将炸弹猫放回第 {pos} 位 (0~{len(self.deck.cards)})")
                self.deck.insert_card(bomb_card, pos)
                self.ai_known.insert(pos, bomb_card)  # 同步更新 AI 对牌堆的认知
            else:
                # GUI处理玩家选择
                if self.gui:
                    pos = self.gui.prompt_bomb_position(len(self.deck.cards))
                    if pos is not None:
                        self.deck.insert_card(bomb_card, pos)
                        self.ai_known.insert(pos, "unknown")
                    else:
                        # 默认放在随机位置
                        pos = random.randint(0, len(self.deck.cards))
                        if self.gui:
                            self.gui.print(f"默认将炸弹猫放回第 {pos} 位 (0~{len(self.deck.cards)})")
                        self.deck.insert_card(bomb_card, pos)
                        self.ai_known.insert(pos, "unknown")

            if self.gui and self.remaining_turns > 1:
                self.gui.print(f"💣⏭️ {player.name} 剩余的 {self.remaining_turns - 1} 个回合全部结束")

        else:
            if self.gui:
                self.gui.print(f"💥 {player.name} 没有拆除卡！爆炸了！")
            player.alive = False
            self.check_game_end()

    def _end_turn(self):
        """结束回合处理，启动下一个回合"""
        if self.all_end:  # 如果抽到炸弹猫拆掉/出SuperSkip，结束所有回合
            self.all_end = False
            self.remaining_turns = 1
            self.current_player = self.get_other(self.current_player)
        elif self.remaining_turns > 0:
            self.remaining_turns -= 1
            if self.remaining_turns == 0:
                self.remaining_turns = 1
                self.current_player = self.get_other(self.current_player)

        # 先检查游戏是否已经结束！多输出“── 👤 玩家回合 ──”的问题在这
        self.check_game_end()
        if self.gui:
            self.gui.update_gui()

        # 如果游戏还在进行，切换到下一个玩家
        # 游戏如果结束了，上面check_game_end其实不会拦截，只会显示游戏结束信息和禁用按钮，靠这里复核来截停AI回合（不开始schedule_ai_turn）
        if self.gui and self.game_running and self.ai.alive and self.player.alive:
            if self.current_player.is_ai:
                self.gui.draw_button.config(state=tk.DISABLED)
                self.gui.play_button.config(state=tk.DISABLED)
                self.gui.schedule_ai_turn()
            else:
                self.gui.schedule_player_turn()

    def check_game_end(self):
        """检查游戏是否结束"""
        # game_running保证只能进来一次
        if (not self.player.alive or not self.ai.alive) and self.game_running:
            if self.gui:
                self.game_running = False  # 先停止game_running，否则在game_end中会被拦截！
                self.gui.game_end()
            return True
        return False

    def get_other(self, player):
        """获取对手实例"""
        return self.ai if player == self.player else self.player


class GUI:
    """图形用户界面类"""

    def __init__(self, _root, debug_mode=False):
        # 设置窗口属性
        self.root = _root

        # 界面变量
        self.player_cards_var = None
        self.ai_cards_var = None
        self.player_cards = None

        # UI组件
        self.turn_label = None
        self.deck_label = None
        self.bomb_label = None
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
        windll.user32.ShowWindow(windll.kernel32.GetConsoleWindow(), self.debug_mode)  # 根据 debug_mode 决定是否隐藏命令行窗口
        self.print("[🐱 BombCat 炸弹猫]\n欢迎来到 BombCat！\n")

    def set_game(self, game):
        """设置游戏引用"""
        # 解决Game和GUI类交叉依赖的解决方法！
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

        # 更新初始界面
        self.print("[🐱 BombCat 炸弹猫]\n游戏开始！\n\n────────── 👤 玩家回合 ──────────\n🧠 玩家 正在思考...")
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
        color = "blue" if self.game.current_player == self.game.player else "black"  # 红色字体表示玩家回合
        self.turn_label.config(foreground=color, text=f"当前回合: {current} (剩余{self.game.remaining_turns}回合)")
        self.deck_label.config(text=f"牌堆剩余: {len(self.game.deck.cards)}张")

        bomb_prob = self.game.deck.amounts[BombCatCard] / len(self.game.deck.cards)
        color = "darkred" if bomb_prob > 0.5 else "red" if bomb_prob > 0.4 else "orange" if bomb_prob > 0.3 else "green"
        self.bomb_label.config(foreground=color, text=f"💣 {bomb_prob if bomb_prob <= 1 else 1:.1%}")

        self.mode_label.config(text=f"游戏模式: {'Debug' if self.debug_mode else '正常'}")
        player_status = "存活" if self.game.player.alive else "死亡"
        ai_status = "存活" if self.game.ai.alive else "死亡"

        self.player_status.config(text=f"玩家状态: {player_status}")
        self.ai_status.config(text=f"AI状态: {ai_status}")

        self.root.update()

    # noinspection SpellCheckingInspection
    def init_window(self):
        """创建并初始化GUI窗口"""
        # 设置窗口标题和大小
        self.root.attributes("-topmost", True)  # 设置窗口置顶，下面再取消强制置顶
        self.root.title("BombCat by Infinovast @Github")
        self.root.resizable(True, True)
        self.root.attributes("-topmost", False)  # 取消强制置顶

        # 窗口居中
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = 800
        window_height = 600
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.update_idletasks()  # 更新窗口信息

        # 创建主窗口框架
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill="both", expand=True)

        # 状态区域
        status = ttk.LabelFrame(main, text="游戏状态", padding="5")
        status.pack(fill="x", pady=5)
        labels = [("turn_label", "当前回合: 未开始"), ("deck_label", "牌堆剩余: 0"),
                  ("bomb_label", "💣 0.0%"), ("player_status", "玩家状态: 存活"),
                  ("ai_status", "AI状态: 存活"), ("mode_label", "游戏模式: 正常")
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
            side: Literal["left", "right", "top", "bottom"]  # 明确类型
            frame = ttk.LabelFrame(hands, text=f"{name}手牌", padding="5")
            frame.pack(side=side, fill="both", expand=True)

            var_name = f"{'player' if is_player else 'ai'}_cards_var"
            setattr(self, var_name, tk.StringVar())
            label = ttk.Label(frame, textvariable=getattr(self, var_name))
            if is_player:
                self.player_cards = label
                label.configure(wraplength=650)
            label.pack(fill="both", expand=True)

        # 按钮区域
        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=5)

        button_sections = [
            ("left", "游戏控制", [("start_button", "开始游戏", self.start_game, {}),
                              ("quit_button", "退出游戏", self.quit_game, {})]),
            ("right", "玩家操作", [("draw_button", "抽牌", self.player_draw, {"state": "disabled"}),
                                   ("play_button", "出牌", self.player_play, {"state": "disabled"})]),
        ]

        for side, title, buttons in button_sections:
            frame = ttk.LabelFrame(actions, text=title, padding="5")
            frame.pack(side=side, fill="x", expand=True, anchor="w")
            for attr, text, cmd, opts in buttons:
                btn = ttk.Button(frame, text=text, command=cmd, **opts)
                setattr(self, attr, btn)
                btn.pack(side="left", padx=5, expand=True)

        self.quit_button.bind('<Button-3>', lambda e: self.toggle_debug_mode())  # 绑定右键单击为切换调试模式

    def player_draw(self):
        """处理玩家抽牌"""
        if not self.game:
            return

        if self.game.current_player != self.game.player:
            messagebox.showinfo("提示", "❌ 现在不是你的回合！")
            return

        if len(self.game.player.hand) >= self.game.player.hand_limit:
            messagebox.showinfo("提示", f"🈵 手牌已满 (上限为{self.game.player.hand_limit}张)，请先出牌！")
            return

        self.game.draw_card(self.game.player)

    def player_play(self):
        """处理玩家出牌"""
        if not self.game:
            return
        if self.game.current_player.is_ai:
            np = self.game.ai.get_specific_cards(NopeCard)
            if np and messagebox.askyesno("提示", f"现在不是你的回合！是否要提前打出拒绝卡？（你有{len(np)}张）"):
                self.game.play_card(self.game.player, np)
            else:
                messagebox.showinfo("提示", "❌ 现在不是你的回合！")
            return

        player = self.game.player
        cards = player.get_specific_cards('playable')
        if not cards:
            messagebox.showinfo("提示", "🈳 没有可用的卡牌")
            return

        # 创建卡牌选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("选择卡牌")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # 在主窗口上居中显示对话框
        x = self.root.winfo_x() + self.root.winfo_width() // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f'+{x}+{y}')
        dialog.update_idletasks()

        # 创建卡牌列表
        tk.Label(dialog, text="🃏 选择要使用的卡牌:").pack(pady=10)
        card_list = tk.Listbox(dialog, height=10, width=50)
        card_list.pack(fill="both", expand=True, padx=10, pady=5)

        for i, card in enumerate(cards):
            card_list.insert(tk.END, f"{i + 1}. {getattr(card, 'name', '未知卡牌')}: {getattr(card, 'description', '无描述')}")

        def use_selected_card():
            """使用选中的卡牌"""
            selection = card_list.curselection()
            if not selection:
                messagebox.showinfo("提示", "🈳 请先选择一张卡牌")
                return

            index = selection[0]
            self.game.play_card(player, cards[index])  # 调用游戏逻辑处理出牌
            dialog.destroy()

        # 绑定双击事件
        card_list.bind('<Double-1>', lambda e: use_selected_card())

        # 添加按钮
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill="x", pady=5)
        tk.Button(btn_frame, text="确认", command=use_selected_card, width=10, height=5).pack(side="left", padx=10, expand=True)
        tk.Button(btn_frame, text="取消", command=dialog.destroy, width=10, height=5).pack(side="right", padx=10, expand=True)

    def toggle_debug_mode(self, config=None):
        """切换调试模式"""
        if config:
            self.debug_mode = config
        else:
            self.debug_mode = not self.debug_mode
        self.update_gui()
        windll.user32.ShowWindow(windll.kernel32.GetConsoleWindow(), self.debug_mode)  # 根据 debug_mode 决定是否隐藏命令行窗口
        messagebox.showinfo("Debug模式", f"💻 Debug模式{'开启' if self.debug_mode else '关闭'}")

    def prompt_bomb_position(self, max_pos):
        """提示玩家选择炸弹猫放回位置"""
        pos = simpledialog.askinteger("选择位置", f"💣 将炸弹猫放回的位置 (底部 0-顶部 {max_pos})：", minvalue=0, maxvalue=max_pos)
        if pos is not None:
            self.print(f"📍 将炸弹猫放回第 {pos} 位")
        return pos

    def schedule_ai_turn(self):
        """安排AI回合"""
        if self.game.current_player.is_ai and self.game.ai.alive:  # 和run_ai_turn双保险
            self.print("\n────────── 🤖 AI回合 ──────────\n💡 AI 正在思考...")
        self.root.after(1000, self.game.run_ai_turn)  # 延迟后执行AI回合

    def schedule_player_turn(self):
        """安排玩家回合"""
        self.print("\n────────── 👤 玩家回合 ──────────\n🧠 玩家 正在思考...")
        def enable_button():
            self.draw_button.config(state=tk.NORMAL)
            self.play_button.config(state=tk.NORMAL)
        self.root.after(500, enable_button)  # 延迟后启用玩家操作按钮

    def game_end(self):
        """游戏结束处理"""
        if not self.game or self.game.game_running:
            return

        self.print("\n────────── 🎮 游戏结束 ──────────")

        if self.game.player.alive and not self.game.ai.alive:
            self.print("🎉 恭喜！玩家获胜！")
            messagebox.showinfo("游戏结束", "你赢了！")
        elif self.game.ai.alive and not self.game.player.alive:
            self.print("😢 AI 获胜！")
            messagebox.showinfo("游戏结束", "AI赢了！")
        else:
            self.print("😐 平局！")
            messagebox.showinfo("游戏结束", "平局！")

        self.print("🎉 感谢游玩！按 [开始游戏] 重新开始或 [退出游戏] 退出...")

        # 禁用游戏操作按钮
        self.draw_button.config(state=tk.DISABLED)
        self.play_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)
        # 禁用操作按钮之后，如果是玩家回合已经无法进行；
        # 如果是AI回合，则会因为game_running=False导致_end_turn最后的schedule_ai_turn执行不到，也无法进行

    def quit_game(self):
        """退出游戏"""
        if messagebox.askyesno("确认", "确定要退出游戏吗？"):
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    GUI(root, debug_mode=False)
    root.mainloop()
