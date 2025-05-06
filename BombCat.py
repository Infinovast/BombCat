"""
BombCat
爆炸猫游戏卡牌库

规则说明：
1. 初始手牌6张，其中1张必为拆除卡；手牌上限9张
2. 抽到炸弹猫时必须使用拆除卡才能存活，否则立即死亡
3. 攻击卡可使对手连续执行多个回合，跳过卡可跳过一个回合
4. 牌堆用完后会自动使用弃牌堆重新洗牌

新增卡牌步骤：
   a. 创建继承自Card的子类
   b. 在Deck._initialize_cards中添加卡牌数量
   c. 在卡牌类中实现use方法处理效果
"""
from tkinter import simpledialog, messagebox

class Card:
    """卡牌基类"""

    def __init__(self, name, description):
        self.name = name
        self.description = description

    def use(self, game, player, target):
        """使用卡牌效果，需在子类实现"""
        raise NotImplementedError("必须实现use方法")


class BombCatCard(Card):
    """炸弹猫卡"""

    def __init__(self):
        super().__init__("炸弹猫", "抽到时必须立即拆除，否则死亡")

    def use(self, game, player, target):
        # 实际处理逻辑在抽牌阶段实现
        pass

class DefuseCard(Card):
    """拆除卡"""

    def __init__(self):
        super().__init__("拆除", "拆除炸弹猫并放回牌堆")

    def use(self, game, player, target):
        # 实际处理逻辑在抽牌阶段实现
        pass

class AttackCard(Card):
    """攻击卡"""

    def __init__(self):
        super().__init__("攻击", "让对手执行你的所有回合")

    def use(self, game, player, target):
        game.gui.print(f"🔥 {player.name} 发动攻击！{target.name} 将要连续行动 {game.remaining_turns + 1} 回合")
        game.remaining_turns += 2  # 在当前回合基础上加2个回合，因为原有的回合会在handle_turn结束后减掉
        game.current_player = target
        game.end_turn = True
        
        # 关键修复：如果目标是AI，则立即调度AI回合
        if target.is_ai and game.gui:
            game.gui.schedule_ai_turn()

class SkipCard(Card):
    """跳过卡"""

    def __init__(self):
        super().__init__("跳过", "跳过当前回合的抽牌阶段")

    def use(self, game, player, target):
        game.gui.print(f"⏭️ {player.name} 跳过了回合")
        game.end_turn = True

class ShuffleCard(Card):
    """洗牌卡"""

    def __init__(self):
        super().__init__("洗牌", "重新洗牌整个牌堆")

    def use(self, game, player, target):
        game.gui.print("🃏 牌堆被重新洗牌！")
        game.deck.shuffle()
        game.ai_known = ["unknown"] * len(game.deck.cards)  # 洗牌后 AI 对所有牌的信息全部失效

class SwapCard(Card):
    """顶底互换卡"""

    def __init__(self):
        super().__init__("顶底互换", "交换牌堆顶部和底部的牌")

    def use(self, game, player, target):
        if len(game.deck.cards) > 1:
            game.gui.print(f"🔄 {player.name} 交换了牌堆顶部和底部的牌")
            game.deck.cards[0], game.deck.cards[-1] = game.deck.cards[-1], game.deck.cards[0]
            game.ai_known[0], game.ai_known[-1] = game.ai_known[-1], game.ai_known[0]  # 同步交换 AI 已知信息
        else:
            game.gui.print("😔 牌堆中牌不足，无法进行顶底互换")

class DrawBottomCard(Card):
    """抽底卡"""

    def __init__(self):
        super().__init__("抽底", "抽取牌堆底部的牌而不是顶部")

    def use(self, game, player, target):
        game.gui.print(f"👇 {player.name} 从牌堆底部抽牌")
        game.draw_card(player, from_bottom=True)  # draw_card 会自动结束回合 和 记录ai_known

class SeeFutureCard(Card):
    """预见未来卡"""

    def __init__(self):
        super().__init__("预见未来", "查看牌堆顶的3张牌")

    def use(self, game, player, target):
        top_count = min(len(game.deck.cards), 3)
        if top_count == 0:
            game.gui.print(f"😮 牌堆里没有牌了！")
            return

        top_cards = list(reversed(game.deck.cards[-top_count:]))  # 获取顶部的牌
        game.gui.print(f"🔮 {player.name} 查看了牌堆顶的{top_count}张牌")

        # AI：记录这 top_count 张牌的实例
        if player.is_ai:
            for i, card in enumerate(top_cards):
                idx = len(game.deck.cards) - 1 - i
                game.ai_known[idx] = card
            game.gui.print(f"🤖 AI 记录了牌堆顶{top_count}张牌的信息")
        # 玩家
        else:
            cards_info = [f"{i + 1}. {card.name}" for i, card in enumerate(top_cards)]
            game.gui.print("🔽 牌堆顶的牌（从上到下）:")
            for info in cards_info:
                game.gui.print(info)

class AlterFutureCard(Card):
    """改变未来卡"""

    def __init__(self):
        super().__init__("改变未来", "查看并排序牌堆顶的3张牌")

    def use(self, game, player, target):
        top_count = min(len(game.deck.cards), 3)
        top_cards = list(reversed(game.deck.cards[-top_count:]))  # 反转顺序
        game.deck.cards = game.deck.cards[:-top_count]  # 移除这些牌
        del game.ai_known[-top_count:]  # 同步删除 ai_known 顶部 top_count 条目

        game.gui.print(f"🔄 {player.name} 正在重新排列牌堆顶的{top_count}张牌")

        # AI逻辑：将爆炸猫（如果有）放在第2张位置
        if player.is_ai:
            bomb_cats = [i for i, card in enumerate(top_cards) if isinstance(card, BombCatCard)]
            if bomb_cats and top_count > 1:
                bomb_idx = bomb_cats[0]
                if top_count >= 2:
                    if game.remaining_turns == 1:
                        top_cards[bomb_idx], top_cards[-2] = top_cards[-2], top_cards[bomb_idx]
                    else:  # 如果下回合还是 AI，则放在最后一张
                        top_cards[bomb_idx], top_cards[-1] = top_cards[-1], top_cards[bomb_idx]
                    game.gui.print("🤖 AI重新排列了牌堆顶的牌")

            # 将排序后的牌放回牌堆
            for card in top_cards:  # 倒序添加以保持原先的顺序
                game.deck.cards.append(card)
            game.ai_known.extend(top_cards)  # AI 知道新顺序，直接写入 card 对象

        # 玩家逻辑：使用tkinter对话框让玩家重新排序卡牌
        else:
            # 创建卡牌列表和对话框
            cards_info = [f"{i + 1}. {card.name}" for i, card in enumerate(top_cards)]
            result = simpledialog.askstring(
                "重新排序卡牌",
                f"🔁 请输入新的顺序（{', '.join(cards_info)}）\n🔢 输入数字序列，用空格分隔（例如：3 1 2）：",
                parent=game.gui.root  # 设置出牌菜单为主窗口
            )

            try:
                if result:
                    order = result.strip().split()
                    if len(order) != top_count:
                        messagebox.showwarning("无效输入", f"请输入{top_count}个数字")
                        order = [str(i+1) for i in range(top_count)]  # 默认顺序

                    indices = [int(x) - 1 for x in order]
                    if any(i < 0 or i >= top_count for i in indices) or len(set(indices)) != top_count:
                        messagebox.showwarning("无效输入", "输入的数字无效")
                        indices = list(range(top_count))  # 默认顺序

                    # 根据玩家的输入重新排序
                    reordered = [top_cards[i] for i in indices]
                else:
                    # 用户取消，保持原顺序
                    reordered = top_cards
            except (ValueError, IndexError):
                messagebox.showwarning("输入错误", "格式错误，使用原始顺序")
                reordered = top_cards

            # 将排序后的牌放回牌堆
            game.gui.print("🔽 现在牌堆顶的牌（从上到下）:")
            cards_info = [f"{i + 1}. {card.name}" for i, card in enumerate(reordered)]
            for info in cards_info:
                game.gui.print(info)
            for card in reversed(reordered):
                game.deck.cards.append(card)

            # 更新 AI 已知信息
            game.ai_known.extend(["unknown"] * top_count)  # 玩家重排后，AI 不知道新顺序
