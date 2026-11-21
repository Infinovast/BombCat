"""
炸弹猫游戏的图形界面实现
"""
import queue
import re
from tkinter import ttk, messagebox
from cards import *
import ai_player as ai_behavior
from game_controller import Game, Player


class _LogLine(str):
    """Keep display styling separate from the visible log text."""

    def __new__(cls, text, *, debug=False):
        line = super().__new__(cls, text)
        line.debug = debug
        return line


class GUI:
    """图形用户界面类"""

    def __init__(self, _root, debug_mode=False):
        # 设置窗口属性
        self.root = _root
        self.debug_mode = debug_mode
        self._ai_paused = False

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
        welcome_text = (
            f"[🐱 BombCat 炸弹猫]\n"
            f"欢迎来到 BombCat！\n"
            f"作者：Infinovast @Github\n\n"
            f"规则：\n"
            f"1. 开局双方各 {Player('').init_limit} 张手牌（含 1 张拆除），手牌上限 {Player('').hand_limit} 张。\n"
            f"2. 在你的回合任意 🃏出牌，而 ✋抽牌 会结束本回合。\n"
            f"3. 回合交替进行，直到抽到 💣炸弹猫 且无 🛠拆除则死亡，最终存活者获胜。\n\n"
            f"卡牌：\n"
            f"· 拒绝：让对手下一张出牌失效。\n"
            f"· 攻击 / 自我攻击：增加并转移（或保留）连续行动回合。\n"
            f"· 跳过 / 超级跳过：跳过当前回合抽牌，或直接跳过剩余全部回合。\n"
            f"· 预见未来 / 改变未来：查看或操控牌堆顶部顺序。\n"
            f"· 抽底 / 顶底互换 / 洗牌：改变抽牌位置或牌序。\n"
            f"说明：\n"
            f"1. 按钮[开始游戏]：左键 / 右键重开游戏（Debug 模式下）。\n"
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
        if debug and not self.debug_mode:
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
                self._ingest_log_message(message, debug=debug)
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

    def _append_log_line(self, line, debug=False):
        if not self.current_turn_log:
            self._start_turn_log("system", "📣 系统消息")

        if not self.current_turn_log["blocks"]:
            self.current_turn_log["blocks"].append([])

        self.current_turn_log["blocks"][-1].append(_LogLine(line, debug=debug))

    def _start_log_block(self):
        if not self.current_turn_log:
            return
        if not self.current_turn_log["blocks"]:
            self.current_turn_log["blocks"].append([])
            return
        if self.current_turn_log["blocks"][-1]:
            self.current_turn_log["blocks"].append([])

    def _ingest_log_message(self, message, debug=False):
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        for line in lines:
            role, title = self._parse_turn_header(line)
            if role:
                self._start_turn_log(role, title)
                continue

            if self._is_block_separator(line):
                self._start_log_block()
                continue

            self._append_log_line(line, debug=debug)

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
                ("将炸弹猫放回" in block_text or "默认将炸弹猫放回" in block_text or
                 f"将{Game._card_short_name(BombCatCard())}放回" in block_text)):
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
                        tag = "debug_body" if getattr(content, "debug", False) else f"{role}_body"
                        if content in ("规则：", "说明：", "卡牌："):
                            self.log_text.insert("end", f"  │ {content}\n", "system_section")
                        else:
                            self.log_text.insert("end", f"  │ {content}\n", tag)
                    self.log_text.insert("end", "  └────────────────\n", f"{role}_block")
                else:
                    block_title = self._get_block_title(block)
                    self.log_text.insert("end", f"  ├─ {block_title}\n", f"{role}_block")
                    for content in block:
                        tag = "debug_body" if getattr(content, "debug", False) else f"{role}_body"
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
        self.root.title("BombCat")
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

        deck_count = len(self.game.deck.cards)
        show_probability = deck_count > 0 and self.game.core.phase == "Play"
        bomb_prob = self.game.deck.amounts[BombCatCard] / deck_count if show_probability else 0
        color = "darkred" if bomb_prob > 0.5 else "red" if bomb_prob > 0.4 else "orange" if bomb_prob > 0.3 else "green"
        self.bomb_label.config(foreground=color if show_probability else "gray",
                               text=f"💣 {bomb_prob if bomb_prob <= 1 else 1:.1%}" if show_probability else "💣 —")

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
            restart = no_ask
            if not no_ask:
                self._ai_paused = True
                try:
                    restart = messagebox.askyesno("确认", "游戏正在进行，是否重新开始？")
                finally:
                    self._ai_paused = False
            if restart:
                ai_behavior.cancel_search(self.game)
                self.game = Game(gui=self)  # 初始化，但不重新创建GUI
            else:
                return
        elif not self.game.ai.alive or not self.game.player.alive:
            ai_behavior.cancel_search(self.game)
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
            game = self.game
            self.root.after_idle(lambda: game.play_card(game.player, selected_card))

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
        print(f"Debug模式{'开启' if self.debug_mode else '关闭'}")
        messagebox.showinfo("Debug模式", f"Debug模式{'开启' if self.debug_mode else '关闭'}")

    def prompt_bomb_position(self, max_pos):
        """提示玩家选择炸弹猫放回位置"""
        total_positions = max_pos + 1
        result = {"pos": None, "rank": None}
        selected_rank = {"value": None}
        position_buttons = []
        rank_entry = None

        def rank_to_pos(rank):
            # 牌堆内部以0为底部、max_pos为顶部；弹窗使用从上到下的直觉顺序。
            return max_pos - rank + 1

        def rank_label(rank):
            if total_positions > 3 and rank >= total_positions - 2:
                reverse_rank = total_positions - rank + 1
                if reverse_rank == 1:
                    return f"倒数第 {reverse_rank} 张（底部）"
                return f"倒数第 {reverse_rank} 张"
            if rank == 1:
                return f"第 {rank} 张（顶部）"
            if rank == total_positions:
                return f"第 {rank} 张（底部）"
            return f"第 {rank} 张"

        def select_rank(rank):
            selected_rank["value"] = rank
            if rank_entry is not None:
                rank_entry.delete(0, tk.END)
            for btn_rank, btn in position_buttons:
                btn.config(bg="lightblue" if btn_rank == rank else "SystemButtonFace")

        def confirm_rank(rank):
            result["rank"] = rank
            result["pos"] = rank_to_pos(rank)
            dialog.destroy()

        def confirm_selection(event=None):
            value = rank_entry.get().strip() if rank_entry is not None else ""
            if value:
                try:
                    rank = int(value)
                except ValueError:
                    messagebox.showinfo("提示", f"请输入 1 到 {total_positions} 之间的整数", parent=dialog)
                    rank_entry.focus_set()
                    rank_entry.select_range(0, tk.END)
                    return event

                if not 1 <= rank <= total_positions:
                    messagebox.showinfo("提示", f"请输入 1 到 {total_positions} 之间的整数", parent=dialog)
                    rank_entry.focus_set()
                    rank_entry.select_range(0, tk.END)
                    return event

                confirm_rank(rank)
                return event

            if selected_rank["value"] is None:
                messagebox.showinfo("提示", "请选择一个位置", parent=dialog)
                return event

            confirm_rank(selected_rank["value"])
            return event

        dialog = tk.Toplevel(self.root)
        dialog.title("放回炸弹猫")
        dialog.transient(self.root)
        dialog.grab_set()

        height = 350 if max_pos > 6 else max(250, 145 + total_positions * 34)
        dialog.geometry(f"360x{height}")

        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 180
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - height // 2
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="💣 选择炸弹猫放回的位置（从上到下）：").pack(pady=(12, 8))

        deck_frame = tk.Frame(dialog)
        deck_frame.grid_columnconfigure(0, weight=1)
        deck_frame.pack(fill="x", padx=24, pady=(2, 4))

        def add_position_button(rank):
            btn = tk.Button(
                deck_frame,
                text=rank_label(rank),
                width=32,
                height=1,
                anchor="center",
                justify="center",
                command=lambda r=rank: select_rank(r),
            )
            btn.grid(row=deck_frame.grid_size()[1], column=0, sticky="ew", pady=2)
            position_buttons.append((rank, btn))

        if max_pos > 6:
            for rank in range(1, 4):
                add_position_button(rank)

            middle_frame = tk.Frame(deck_frame, pady=6)
            middle_frame.grid(row=deck_frame.grid_size()[1], column=0, sticky="ew")
            middle_frame.grid_columnconfigure(1, weight=1)

            tk.Label(middle_frame, text="中间：第").grid(row=0, column=0, sticky="e")
            rank_entry = tk.Entry(middle_frame, width=8, justify="center", font=("Microsoft YaHei", 13))
            rank_entry.grid(row=0, column=1, sticky="ew", padx=6, ipady=5)
            tk.Label(middle_frame, text="张").grid(row=0, column=2, sticky="w")

            rank_entry.bind("<Return>", confirm_selection)
            rank_entry.focus_set()

            for rank in range(total_positions - 2, total_positions + 1):
                add_position_button(rank)
        else:
            for rank in range(1, total_positions + 1):
                add_position_button(rank)

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill="x", pady=(2, 10))
        tk.Button(btn_frame, text="确认", command=confirm_selection, width=12, height=1).pack(side="left", padx=(24, 8), expand=True)
        tk.Button(btn_frame, text="随机位置", command=dialog.destroy, width=12, height=1).pack(side="right", padx=(8, 24), expand=True)

        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.wait_window()

        if result["pos"] is not None:
            self.print(f"📌 将炸弹猫放回从上到下{rank_label(result['rank'])}")
        return result["pos"]

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
        self._ai_paused = True
        try:
            quit_confirmed = messagebox.askyesno("确认", "确定要退出游戏吗？")
        finally:
            self._ai_paused = False
        if quit_confirmed:
            ai_behavior.cancel_search(self.game)
            self.root.destroy()


def main():
    """主函数"""
    root = tk.Tk()
    gui = GUI(root, debug_mode=False)
    root.protocol("WM_DELETE_WINDOW", gui.quit_game)
    root.mainloop()

if __name__ == "__main__":
    main()
