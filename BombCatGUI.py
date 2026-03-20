"""
炸弹猫游戏的图形界面实现
"""
import queue
import random
import re
from tkinter import ttk, messagebox, simpledialog
from BombCat import *
import ai as ai_behavior


class Deck:
    """牌堆管理器"""

    def __init__(self):
        self.cards = []
        self.discard_pile = []
        self.amounts = {
            BombCatCard: 4, DefuseCard: 4, NopeCard: 3, AttackCard: 4, PersonalAttackCard: 3,
            SkipCard: 3, SuperSkipCard: 2, ShuffleCard: 2, SeeFutureCard: 2, AlterFutureCard: 3,
            DrawBottomCard: 2, SwapCard: 2
        }
        self._initialize_cards()
        self.shuffle()

    def _initialize_cards(self):
        # 卡牌配置区（可在此添加新卡牌）
        cards = [
            *[BombCatCard() for _ in range(self.amounts[BombCatCard])],  # 炸弹猫
            *[DefuseCard() for _ in range(self.amounts[DefuseCard])],  # 拆除卡
            *[NopeCard() for _ in range(self.amounts[NopeCard])],  # 拒绝卡
            *[AttackCard() for _ in range(self.amounts[AttackCard])],  # 攻击卡
            *[PersonalAttackCard () for _ in range(self.amounts[PersonalAttackCard])],  # 自我攻击卡
            *[SkipCard() for _ in range(self.amounts[SkipCard])],  # 跳过卡
            *[SuperSkipCard() for _ in range(self.amounts[SuperSkipCard])],  # 超级跳过卡
            *[ShuffleCard() for _ in range(self.amounts[ShuffleCard])],  # 洗牌卡
            *[SeeFutureCard(depth=random.choices([3, 5], weights=[4, 1])[0])
                  for _ in range(self.amounts[SeeFutureCard])],  # 预见未来卡
            *[AlterFutureCard(depth=random.choices([3, 5], weights=[4, 1])[0])
                  for _ in range(self.amounts[AlterFutureCard])],  # 改变未来卡
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
        self.init_limit = 6  # 设置初始手牌上限
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

    def hand_text(self):
        """获取手牌文本"""
        hand_tmp = {c.name: len([x for x in self.hand if x.name == c.name]) for c in self.hand}
        hand_tmp = sorted(hand_tmp.items(), key=lambda item: (0 if item[0] == DefuseCard().name else 1, item[0]))
        text = ""
        for name, amt in hand_tmp:
            text += f"{name} ×{amt} | "
        return text[:-3]  # 去掉最后的[-3~-1] " | "


class Game:
    """
    游戏控制器
    没有显式主循环，游戏循环实际上由_next_turn()推动
    """

    def __init__(self, gui=None):
        self.deck = Deck()  # 创建Deck(牌堆)实例
        self.player = Player("玩家")  # 创建Player(玩家)实例
        self.ai = Player("AI", is_ai=True)  # 创建Player(AI)实例
        self.gui = gui  # 保存GUI引用，用于更新界面

        # 有关回合
        self._init_hands()
        self.remaining_turns = 1
        self.current_player = self.player
        self.end_turn = False
        self.end_all_turn = False
        self.game_running = False  # Game初始化的时候游戏未开始，在start_game()中才设置为True
        self.turn_owner = self.current_player
        self.turn_progress = 1
        self.turn_total = self.remaining_turns

        self.ai_known = []
        self.ai_init_knowledge()
        self.noped = None  # =None 无人被Nope | self.player 对玩家生效 | self.ai 对AI生效

        gui.set_game(self)  # 设置GUI内部对game的引用

    def _init_hands(self):
        """初始化双方手牌"""
        for p in [self.player, self.ai]:
            p.hand.append(DefuseCard())  # 强制加入一张拆除卡
            p.hand.extend(self.deck.draw(p.init_limit - 1 , refuse=[BombCatCard()]))  # 再抽5张牌 6-1=5

    @staticmethod
    def _card_short_name(card):
        """用于Debug牌堆预览的卡牌简称。"""
        if isinstance(card, BombCatCard):
            return "炸"
        if isinstance(card, DefuseCard):
            return "拆"
        if isinstance(card, NopeCard):
            return "阻"
        if isinstance(card, AttackCard):
            return "攻"
        if isinstance(card, PersonalAttackCard):
            return "自"
        if isinstance(card, SkipCard):
            return "跳"
        if isinstance(card, SuperSkipCard):
            return "超"
        if isinstance(card, ShuffleCard):
            return "洗"
        if isinstance(card, SwapCard):
            return "换"
        if isinstance(card, DrawBottomCard):
            return "底"
        if isinstance(card, SeeFutureCard):
            return "预5" if getattr(card, "depth", 3) == 5 else "预"
        if isinstance(card, AlterFutureCard):
            return "改5" if getattr(card, "depth", 3) == 5 else "改"
        return "?"

    def print_debug_deck_snapshot(self, top_n=6, bottom_n=3):
        """Debug模式下输出牌堆顶N张和底N张（用简称）。"""
        if not self.gui.debug_mode:
            return

        if not self.deck.cards:
            self.gui.print("牌堆：(空)", debug=True)
            return

        top_count = min(top_n, len(self.deck.cards))
        bottom_count = min(bottom_n, len(self.deck.cards))

        top_cards = list(reversed(self.deck.cards[-top_count:]))  # 顶 -> 下
        bottom_cards = list(reversed(self.deck.cards[:bottom_count]))  # 上 -> 底

        top_text = " ".join(self._card_short_name(c) for c in top_cards)
        bottom_text = " ".join(self._card_short_name(c) for c in bottom_cards)
        separator = "..." if (top_count + bottom_count) < len(self.deck.cards) else " "
        self.gui.print(f"牌堆：{top_text}{separator}{bottom_text}", debug=True)

    def ai_control(self):
        """将 AI 决策委托给独立模块。"""
        return ai_behavior.ai_control(self)

    def ai_turn(self):
        """将 AI 回合执行委托给独立模块。"""
        ai_behavior.ai_turn(self)

    # AI 牌堆认知的统一入口（由 ai.py 提供实现）
    def ai_init_knowledge(self):
        ai_behavior.init_ai_knowledge(self)

    def ai_on_shuffle(self):
        ai_behavior.on_shuffle(self)

    def ai_on_swap_top_bottom(self):
        ai_behavior.on_swap_top_bottom(self)

    def ai_on_draw(self, from_bottom=False):
        ai_behavior.on_draw(self, from_bottom=from_bottom)

    def ai_on_insert_known(self, pos, card):
        ai_behavior.on_insert_known(self, pos, card)

    def ai_on_insert_unknown(self, pos):
        ai_behavior.on_insert_unknown(self, pos)

    def ai_on_see_future(self, top_cards):
        ai_behavior.on_see_future(self, top_cards)

    def ai_on_remove_top(self, top_count):
        ai_behavior.on_remove_top(self, top_count)

    def ai_on_append_known(self, top_cards):
        ai_behavior.on_append_known(self, top_cards)

    def ai_on_append_unknown(self, top_count):
        ai_behavior.on_append_unknown(self, top_count)

    def play_card(self, player, _card):
        """处理双方出牌的底层函数"""
        # 传入的_card可能是单个卡牌，也可能是列表，所以这里统一为单个卡牌
        if isinstance(_card, list):
            card = _card[0]  # 只出一张，且_card列表里面每个元素都一样
        else:
            card = _card  # 这个时候_card就是单个卡牌

        # player打出来的牌被Nope
        if self.noped == player:
            self.noped = None
            self.gui.print(f"🚫 {player.name} 打出的 {card.name} 被 {self.get_other(player).name} 的拒绝卡阻止")
            # 被Nope的牌也要消耗
            player.hand.remove(card)
            self.deck.discard_pile.append(card)
            self.gui.update_gui()
            return True

        self.end_all_turn = False
        if (player == self.current_player or card is NopeCard) and card in player.hand:
            if isinstance(card, NopeCard) and self.noped == self.get_other(player):  # 阻止重复用Nope卡
                if player.is_ai:
                    self.gui.print(f"❌ 已存在 AI 打出的拒绝卡，无法重复打出", debug=True)  # 理论上不会触发
                else:
                    self.gui.print(f"❌ 已存在 玩家 打出的拒绝卡，请勿重复打出")
                return False
            else:
                self.gui.print(f"🎴 {player.name} 使用了 {card.name}")

            player.hand.remove(card)  # 卡牌先消耗手牌再执行效果，针对满牌时用抽底
            card.use(self, player, self.get_other(player))
            self.deck.discard_pile.append(card)
            self.gui.update_gui()

            if self.end_turn or self.end_all_turn:
                # 如果是玩家回合，打开回合结束标记，结束阻塞循环
                if not player.is_ai:
                    self.player_turn_done = True
                self._next_turn()  # 出牌部分的回合结束

            elif not (isinstance(card, NopeCard) and player.is_ai):
                # 间隔下一部分出牌/抽牌文字（都在同一个回合内）
                # 回合只剩1的抽牌/end_turn/end_all_turn为True 不需要间隔，因为回合结束有回合分界线
                self.gui.print("───────/───────")
            return True

        return False

    def draw_card(self, player, from_bottom=False):
        """处理双方抽牌的底层函数"""
        if player != self.current_player:
            return False

        if len(player.hand) >= player.hand_limit:
            self.gui.print(f"🈵 {player.name}手牌已满 (上限为{self.player.hand_limit}张)，请先出牌！")
            return False

        # 从牌堆中抽得drawn列表
        if drawn := self.deck.draw(1, from_bottom=from_bottom):
            self.ai_on_draw(from_bottom=from_bottom)

            card = drawn[0]
            if isinstance(card, BombCatCard):
                # 炸弹流程内部会自行结束回合或结束游戏，避免在此重复推进回合
                self._handle_bomb_cat(player, card)
                self.gui.update_gui()
                return True
            else:
                player.hand.append(card)
                if player.is_ai and not self.gui.debug_mode:
                    self.gui.print(f"🤖 AI 完成抽牌")
                else:
                    self.gui.print(f"🖐 {player.name} 抽到了 {card.name}")
            self.gui.update_gui()

            # 玩家回合结束，结束game._next_turn中的阻塞循环
            if not player.is_ai:
                self.player_turn_done = True
            self._next_turn()  # 抽牌部分的回合结束
            return True
        else:
            self.gui.print("牌堆已空！")
            return False

    def _handle_bomb_cat(self, player, bomb_card):
        """处理炸弹猫逻辑"""
        self.gui.print(f"💣 {player.name} 抽到了炸弹猫！")

        # 不能用use，否则会被Nope拦截
        if player.has_defuse():
            self.gui.print(f"🛠 {player.name} 使用拆除卡...")

            defuse_card = next(c for c in player.hand if isinstance(c, DefuseCard))
            player.hand.remove(defuse_card)
            self.deck.discard_pile.append(defuse_card)

            # 处理放回位置选择
            if player.is_ai:
                pos = random.randint(0, len(self.deck.cards))
                if not self.gui.debug_mode:
                    self.gui.print(f"🤖 AI 将炸弹猫放回牌堆某个位置")
                else:
                    self.gui.print(f"[Debug] AI 将炸弹猫放回第 {pos} 位 (0~{len(self.deck.cards)})")
                self.deck.insert_card(bomb_card, pos)
                self.ai_on_insert_known(pos, bomb_card)
            else:
                # GUI处理玩家选择
                pos = self.gui.prompt_bomb_position(len(self.deck.cards))
                if pos is not None:
                    self.deck.insert_card(bomb_card, pos)
                    self.ai_on_insert_unknown(pos)
                else:
                    # 默认放在随机位置
                    pos = random.randint(0, len(self.deck.cards))
                    self.gui.print(f"📌 随机将炸弹猫放回第 {pos} 位 (0~{len(self.deck.cards)})")
                    self.deck.insert_card(bomb_card, pos)
                    self.ai_on_insert_unknown(pos)

            if self.remaining_turns >= 2:
                self.gui.print(f"💣⏭️ {player.name} 剩余的 {self.remaining_turns - 1} 个回合立即结束")
            self.end_turn = True
            self.end_all_turn = True
            self._next_turn()  # 拆炸弹后一定结束回合

        else:
            self.gui.print(f"💥 {player.name} 没有拆除卡！爆炸了！")
            player.alive = False  # 唯一的死亡入口
            self.check_game_end()

    def _next_turn(self):
        """结束回合，启动下一个回合"""
        prev_player = self.current_player
        self.end_turn = False
        # 抽到炸弹猫拆掉/打出SuperSkip 等，结束所有回合
        if self.end_all_turn:
            self.end_all_turn = False
            self.remaining_turns = 0
        # 没有all_end则回合-1
        else:
            self.remaining_turns -= 1

        # 消耗回合数后，检查是否换边
        if self.remaining_turns <= 0:
            self.remaining_turns = 1
            self.current_player = self.get_other(self.current_player)

        self._advance_turn_counter(switched_player=(self.current_player != prev_player))

        # 先检查游戏是否已经结束！游戏已结束但多输出"─👤玩家回合─"的问题在这
        self.check_game_end()
        self.gui.update_gui()



        # 如果游戏还在进行，切换到下一个玩家
        # 如果游戏结束了，上面check_game_end其实不会拦截，只会显示游戏结束信息和禁用按钮，靠这里复核来截停AI回合（即不开始schedule_ai_turn）
        if self.game_running and self.ai.alive and self.player.alive:
            if self.current_player.is_ai:
                self.gui.draw_button.config(state=tk.DISABLED)  # 这两个按钮在schedule_player_turn再中启用
                self.gui.play_button.config(state=tk.DISABLED)
                self.gui.print(f"\n────────── 🤖 AI回合 {self.get_turn_counter_text()} ──────────\n💡 AI 正在思考...")
                self.print_debug_deck_snapshot()
                self.gui.schedule_ai_turn()  # 唯一接入点！
            else:
                self.gui.print(f"\n────────── 👤 玩家回合 {self.get_turn_counter_text()} ──────────\n🧠 请出牌或抽牌...")
                self.print_debug_deck_snapshot()
                self.gui.draw_button.config(state=tk.NORMAL)
                self.gui.play_button.config(state=tk.NORMAL)

    def _sync_turn_counter(self):
        """同步回合计数器，确保回合内加回合时总回合数实时更新"""
        if self.turn_owner != self.current_player:
            self.turn_owner = self.current_player
            self.turn_progress = 1
            self.turn_total = max(1, self.remaining_turns)
            return

        self.turn_total = max(self.turn_total, self.remaining_turns, self.turn_progress)

    def _advance_turn_counter(self, switched_player):
        """在进入新回合时推进回合计数器"""
        if switched_player or self.turn_owner != self.current_player:
            self.turn_owner = self.current_player
            self.turn_progress = 1
            self.turn_total = max(1, self.remaining_turns)
        else:
            self.turn_progress += 1
            self.turn_total = max(self.turn_total, self.remaining_turns, self.turn_progress)

    def get_turn_counter_text(self):
        """获取用于标题显示的回合计数文本，格式如 1/3"""
        self._sync_turn_counter()
        progress = max(1, self.turn_progress)
        total = max(progress, self.turn_total)
        return f"{progress}/{total}"

    def check_game_end(self):
        """检查游戏是否结束"""
        # 用game_running来保证只能进来一次
        if (not self.player.alive or not self.ai.alive) and self.game_running:
            self.game_running = False  # 停止game_running在前，否则在game_end中会被拦截！
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
        self.debug_mode = debug_mode

        # UI组件
        self.player_cards = None  # 手牌文字所在的Label，是Label对象
        self.ai_cards = None
        self.player_cards_var = None  # 手牌文字，是字符串
        self.ai_cards_var = None

        self.turn_label = None
        self.deck_label = None
        self.bomb_label = None
        self.mode_label = None
        self.player_status = None
        self.ai_status = None
        self.log_text = None
        self.max_turn_logs = 10 if self.debug_mode else 5
        self.log_turns = []
        self.current_turn_log = None

        # 按钮
        self.start_button = None
        self.quit_button = None
        self.draw_button = None
        self.play_button = None

        # 初始化窗口
        self.window_width = 800
        self.window_height = 900
        self.init_window()

        # 游戏引用
        self.game = Game(gui=self)

        # 初始化输出队列，启动线程
        self.print_queue = queue.Queue()
        self.root.after(50, self._process_print_queue)

        # 欢迎文字
        welcome_text = (f"[🐱 BombCat 炸弹猫]\n欢迎来到 BombCat！\n\n"
                        f"规则：\n"
                        f"1. 开局双方各 {Player('').init_limit} 张手牌（包含 1 张拆除卡），手牌上限 {Player('').hand_limit} 张。\n"
                        f"2. 在你的回合可以任意 🃏出牌，而 ✋抽牌 会结束本回合。\n"
                        f"3. 回合交替进行，直到抽到 💣炸弹猫 且无 🛠拆除则死亡，存活者胜利。\n\n"
                        f"卡牌：\n"
                        f"- 拒绝：让对手下一张出牌失效。\n"
                        f"- 攻击 / 自我攻击：增加并转移（或保留）连续行动回合。\n"
                        f"- 跳过 / 超级跳过：跳过当前回合抽牌，或直接跳过剩余全部回合。\n"
                        f"- 预见未来 / 改变未来：查看或操控牌堆顶部顺序。\n"
                        f"- 抽底 / 顶底互换 / 洗牌：改变抽牌位置或牌序。\n"
                        f"说明：\n"
                        f"1. 按钮[开始游戏]：左键 / (Debug 模式下) 右键重开游戏。\n"
                        f"2. 按钮[退出游戏]：右键开关 Debug 模式，查看 AI 思考链、手牌、牌堆等信息。\n"
                        f"3. 游戏日志周围的 UI 会帮助你快速上手游戏。祝您游戏愉快！\n\n"
        )
        self.print(welcome_text, scroll='1.0')

    def set_game(self, game):
        """设置游戏引用"""
        # 解决Game和GUI类交叉依赖的解决方法！
        self.game = game
        self.update_gui()

    def print(self, message, debug=False, scroll='end', delay=0.2):
        """提交输出申请到输出缓存池"""
        # 调试信息只在调试模式下输出
        if debug:
            if self.debug_mode:
                message = f"[Debug] {message}"
            else:
                return

        if message:
            self.print_queue.put((message, debug, scroll, delay))

        # self.log_text.config(state="normal")
        # self.log_text.tag_configure("center", justify="center")  # 定义居中标签
        # self.log_text.insert("end", message + "\n", "center")  # 应用居中标签
        # self.log_text.see(scroll)
        # self.log_text.config(state="disabled")

    def _process_print_queue(self):
        """在主线程轮询输出队列并刷新日志栏"""
        need_render = False
        last_scroll = 'end'
        while not self.print_queue.empty():
            message, debug, scroll, delay = self.print_queue.get()
            last_scroll = scroll

            # 仅在终端输出系统级消息，避免刷出完整游戏日志
            if self.debug_mode:
                self._print_system_message_to_console(message)

            if hasattr(self, 'log_text') and self.log_text:
                self._ingest_log_message(message)
                need_render = True

            self.print_queue.task_done()

        if need_render:
            self._render_structured_logs(scroll=last_scroll)

        # 保持轮询，确保所有UI写操作都在Tk主线程执行
        self.root.after(50, self._process_print_queue)

    def _configure_log_tags(self):
        """配置结构化日志样式标签"""
        self.log_text.tag_configure("turn_sep", foreground="#9AA0A6", justify="center")
        self.log_text.tag_configure("debug_body", foreground="#0B57D0", font=("Microsoft YaHei", 11, "bold"))

        self.log_text.tag_configure("player_header", foreground="#0B5394", background="#E7F1FF", font=("Microsoft YaHei", 12, "bold"))
        self.log_text.tag_configure("player_block", foreground="#3C78D8", font=("Microsoft YaHei", 11, "bold"))
        self.log_text.tag_configure("player_body", foreground="#1F3A5F", font=("Microsoft YaHei", 11))

        self.log_text.tag_configure("ai_header", foreground="#7A3E00", background="#FFF3E8", font=("Microsoft YaHei", 12, "bold"))
        self.log_text.tag_configure("ai_block", foreground="#B45F06", font=("Microsoft YaHei", 11, "bold"))
        self.log_text.tag_configure("ai_body", foreground="#5B3A29", font=("Microsoft YaHei", 11))

        self.log_text.tag_configure("end_header", foreground="#5A3D00", background="#FFF9D6", font=("Microsoft YaHei", 12, "bold"))
        self.log_text.tag_configure("end_block", foreground="#7F6000", font=("Microsoft YaHei", 11, "bold"))
        self.log_text.tag_configure("end_body", foreground="#5A4A14", font=("Microsoft YaHei", 11))

        self.log_text.tag_configure("system_header", foreground="#145A32", background="#EAF7EE", font=("Microsoft YaHei", 12, "bold"))
        self.log_text.tag_configure("system_block", foreground="#1E8449", font=("Microsoft YaHei", 11, "bold"))
        self.log_text.tag_configure("system_body", foreground="#1B4332", font=("Microsoft YaHei", 11))
        self.log_text.tag_configure("system_section", foreground="#0E7A3F", font=("Microsoft YaHei", 11, "bold"))

    @staticmethod
    def _is_block_separator(line):
        stripped = line.strip()
        return bool(stripped) and "/" in stripped and all(c in "─-/" for c in stripped)

    @staticmethod
    def _parse_turn_header(line):
        if "玩家回合" in line:
            return "player", "👤 玩家回合"
        if "AI回合" in line:
            return "ai", "🤖 AI回合"
        if "游戏结束" in line:
            return "end", "🎮 游戏结束"
        return None, None

    def _start_turn_log(self, role, title):
        turn = {
            "role": role,
            "title": title,
            "counter_snapshot": self._get_role_counter_text(role),
            "blocks": [[]]
        }
        self.log_turns.append(turn)
        self.current_turn_log = turn
        if len(self.log_turns) > self.max_turn_logs:
            self.log_turns = self.log_turns[-self.max_turn_logs:]

    def _get_role_counter_text(self, role):
        if not self.game:
            return None
        if role == "player" and self.game.current_player == self.game.player:
            return self.game.get_turn_counter_text()
        if role == "ai" and self.game.current_player == self.game.ai:
            return self.game.get_turn_counter_text()
        return None

    def _render_turn_title(self, turn):
        role = turn["role"]
        title = turn["title"]
        if role not in ("player", "ai"):
            return title

        if self.current_turn_log is turn and self.game and self.game.game_running:
            live_counter = self._get_role_counter_text(role)
            if live_counter:
                return f"{title} {live_counter}"

        if turn.get("counter_snapshot"):
            return f"{title} {turn['counter_snapshot']}"
        return title

    def _append_log_line(self, line):
        if not self.current_turn_log:
            self._start_turn_log("system", "📣 系统消息")

        if not self.current_turn_log["blocks"]:
            self.current_turn_log["blocks"].append([])

        self.current_turn_log["blocks"][-1].append(line)

    def _start_log_block(self):
        if not self.current_turn_log:
            return
        if not self.current_turn_log["blocks"]:
            self.current_turn_log["blocks"].append([])
            return
        if self.current_turn_log["blocks"][-1]:
            self.current_turn_log["blocks"].append([])

    def _ingest_log_message(self, message):
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        for line in lines:
            role, title = self._parse_turn_header(line)
            if role:
                self._start_turn_log(role, title)
                continue

            if self._is_block_separator(line):
                self._start_log_block()
                continue

            self._append_log_line(line)

    @staticmethod
    def _clean_card_name(name):
        # 去掉卡名前面的emoji或符号，仅保留语义文字
        return re.sub(r"^[^\u4e00-\u9fffA-Za-z0-9]+", "", name).strip()

    def _get_block_title(self, block):
        if not block:
            return "常规阶段"

        block_text = "\n".join(block)

        # 规则3：抽炸弹-拆除-放回优先归类为拆弹
        if ("炸弹猫" in block_text and "使用拆除卡" in block_text and
                ("将炸弹猫放回" in block_text or "默认将炸弹猫放回" in block_text)):
            return "拆弹"


        # 规则2.5：检测抽牌操作
        if "抽到了" in block_text or "完成抽牌" in block_text:
            return "抽牌"
        # 规则2：有"使用了 某卡牌"时，标题取卡牌名
        for line in block:
            if "使用了" in line:
                name = line.split("使用了", 1)[1].strip()
                cleaned = self._clean_card_name(name)
                if cleaned:
                    return cleaned

        # 规则1：其余都归常规阶段
        return "常规阶段"

    def _render_structured_logs(self, scroll='end'):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)

        visible_turns = self.log_turns[-self.max_turn_logs:]
        for idx, turn in enumerate(visible_turns):
            role = turn["role"]
            self.log_text.insert("end", f"{self._render_turn_title(turn)}\n", f"{role}_header")

            for block in turn["blocks"]:
                if not block:
                    continue

                if role == "system" or role == "end":
                    for content in block:
                        tag = "debug_body" if content.startswith("[Debug]") else f"{role}_body"
                        if content in ("规则：", "说明：", "卡牌："):
                            self.log_text.insert("end", f"  │ {content}\n", "system_section")
                        else:
                            self.log_text.insert("end", f"  │ {content}\n", tag)
                    self.log_text.insert("end", "  └────────────────\n", f"{role}_block")
                else:
                    block_title = self._get_block_title(block)
                    self.log_text.insert("end", f"  ├─ {block_title}\n", f"{role}_block")
                    for content in block:
                        tag = "debug_body" if content.startswith("[Debug]") else f"{role}_body"
                        self.log_text.insert("end", f"  │ {content}\n", tag)
                    self.log_text.insert("end", "  └────────────────\n", f"{role}_block")

            # if idx < len(visible_turns) - 1:
            #     self.log_text.insert("end", "\n✦──────────────✦\n\n", "turn_sep")

        self.log_text.see(scroll)
        self.log_text.config(state="disabled")

    def _print_system_message_to_console(self, message):
        """仅将关键系统消息输出到终端。"""
        if "游戏开始！" in message:
            print("[SYSTEM] 游戏开始")
        elif "🎮 游戏结束" in message:
            print("[SYSTEM] 游戏结束")
        elif "感谢游玩" in message:
            print("[SYSTEM] 感谢游玩")

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
        x = (screen_width - self.window_width) // 2
        y = (screen_height - self.window_height) // 2
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")
        self.root.update_idletasks()  # 更新窗口信息

        # 创建主窗口框架
        main_window = ttk.Frame(self.root, padding="10")
        main_window.pack(fill="both", expand=True)

        # 状态区域
        status = ttk.LabelFrame(main_window, text="游戏状态", padding="5")
        status.pack(fill="x", pady=5)
        labels = [("turn_label", "当前回合: 未开始"), ("deck_label", "牌堆剩余: 0"),
                  ("bomb_label", "💣 0.0%"), ("player_status", "玩家状态: 存活"),
                  ("ai_status", "AI状态: 存活"), ("mode_label", "游戏模式: 正常")
                  ]
        for i, (attr, text) in enumerate(labels):
            setattr(self, attr, ttk.Label(status, text=text))
            getattr(self, attr).grid(row=0, column=i, padx=10, sticky="w")

        # 日志区域
        log_frame = ttk.LabelFrame(main_window, text="游戏日志", padding="5")
        log_frame.pack(fill="both", expand=True, pady=5)
        self.log_text = tk.Text(log_frame, height=10, width=80, wrap="word", font=("Microsoft YaHei", 12))
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set, state="disabled")
        self._configure_log_tags()

        # 手牌区域
        hands = ttk.Frame(main_window)
        hands.pack(fill="x", pady=5)

        # 玩家手牌
        frame = ttk.LabelFrame(hands, text=f"玩家手牌", padding="5")
        frame.pack(side="left", fill="both", expand=True)
        setattr(self, "player_cards_var", tk.StringVar())
        self.player_cards = ttk.Label(frame, textvariable=self.player_cards_var)
        self.player_cards.configure(
            wraplength=650 if not self.debug_mode else self.window_width // 2)  # 规定玩家手牌区文字的强制换行长度
        self.player_cards.pack(fill="both", expand=True)

        # AI手牌
        frame = ttk.LabelFrame(hands, text=f"AI手牌", padding="5")
        frame.pack(side="right", fill="both", expand=True)
        setattr(self, "ai_cards_var", tk.StringVar())
        self.ai_cards = ttk.Label(frame, textvariable=self.ai_cards_var)
        if self.debug_mode:
            self.ai_cards.configure(wraplength=0 if not self.debug_mode else self.window_width // 2)
        self.ai_cards.pack(fill="both", expand=True)

        # 按钮区域
        actions = ttk.Frame(main_window)
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

        def restart_game(event):
            """重启游戏"""
            if self.debug_mode:
                self.start_game(no_ask=True)
            else:
                messagebox.showinfo("提示", f"调试模式下才能快速重启游戏！（右键 [退出游戏] 开关调试模式）")
            return event
        self.start_button.bind('<Button-3>', restart_game)  # 绑定右键单击开始键为重开游戏（仅在debug模式下有效）
        self.quit_button.bind('<Button-3>', lambda e: self.toggle_debug_mode())  # 绑定右键单击退出键为切换调试模式

    def update_gui(self):
        """更新所有显示"""
        if not self.game:
            return

        # 更新玩家和AI手牌
        self.player_cards.configure(wraplength=680 if not self.debug_mode else 400)  # 规定玩家手牌区文字的强制换行长度 800//2=400
        self.ai_cards.configure(wraplength=0 if not self.debug_mode else 350)  # 规定AI手牌区文字的强制换行长度

        self.player_cards_var.set(f"数量: {len(self.game.player.hand)}张\n{self.game.player.hand_text()}")
        self.ai_cards_var.set(f"数量: {len(self.game.ai.hand)}张{'\n'+self.game.ai.hand_text() if self.debug_mode else ""}")

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

        if self.current_turn_log:
            self._render_structured_logs()

        self.root.update()

    def start_game(self, no_ask=False):
        """启动新游戏/重新启动游戏"""
        if self.game.game_running:
            if no_ask or messagebox.askyesno("确认", "游戏正在进行，是否重新开始？"):
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
        self.log_turns = []
        self.current_turn_log = None

        # 启用玩家操作按钮
        self.draw_button.config(state=tk.NORMAL)
        self.play_button.config(state=tk.NORMAL)
        # self.start_button.config(state=tk.DISABLED)

        # 更新初始界面
        self.print(f"[🐱 BombCat 炸弹猫]\n游戏开始！\n\n────────── 👤 玩家回合 {self.game.get_turn_counter_text()} ──────────\n🧠 请出牌或抽牌...")
        self.game.print_debug_deck_snapshot()
        self.update_gui()

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
            messagebox.showinfo("提示", "❌ 现在不是你的回合！")
            return

        cards = self.game.player.get_specific_cards('playable')
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
        # 让对话框右下角与主窗口右下角对齐
        self.root.update_idletasks()
        # dialog.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() - dialog.winfo_width()
        y = self.root.winfo_y() + self.root.winfo_height() - dialog.winfo_height()
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
            selected_card = cards[index]
            dialog.destroy()

            # 先关闭“选择卡牌”窗口，再执行出牌。
            # 避免抽底触发炸弹时，后续“选择位置”弹窗被前一个grab_set窗口阻塞。
            self.root.after_idle(lambda: self.game.play_card(self.game.player, selected_card))

            # 成功出卡、用卡不一定表示玩家回合结束，不能在这里结束game._next_turn中的阻塞循环
            # 所以在game.play_card中结束game._next_turn中的阻塞循环

        # 绑定双击列表的事件
        card_list.bind('<Double-1>', lambda e: use_selected_card())

        # 添加按钮
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill="x", pady=5)
        tk.Button(btn_frame, text="确认", command=use_selected_card, width=10, height=5).pack(side="left", padx=10, expand=True)
        tk.Button(btn_frame, text="取消", command=dialog.destroy, width=10, height=5).pack(side="right", padx=10, expand=True)

    def toggle_debug_mode(self, config=None):
        """切换调试模式"""
        if config is not None:
            self.debug_mode = config
        else:
            self.debug_mode = not self.debug_mode
        self.max_turn_logs = 10 if self.debug_mode else 5
        if len(self.log_turns) > self.max_turn_logs:
            self.log_turns = self.log_turns[-self.max_turn_logs:]
        self.update_gui()
        print(f"[Debug] Debug模式{'开启' if self.debug_mode else '关闭'}")
        messagebox.showinfo("Debug模式", f"Debug模式{'开启' if self.debug_mode else '关闭'}")

    def prompt_bomb_position(self, max_pos):
        """提示玩家选择炸弹猫放回位置"""
        pos = simpledialog.askinteger("选择位置", f"💣 将炸弹猫放回的位置 (底部 0-顶部 {max_pos})：", minvalue=0, maxvalue=max_pos)
        if pos is not None:
            self.print(f"📌 将炸弹猫放回第 {pos} 位")
        return pos

    def schedule_ai_turn(self):
        """安排AI回合"""

        self.root.after(2000, self.game.ai_turn)  # 延迟后执行AI回合
        # self.game.run_ai_turn()

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


def main():
    """主函数"""
    root = tk.Tk()
    GUI(root, debug_mode=False)
    root.mainloop()

if __name__ == "__main__":
    main()


