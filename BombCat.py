"""
BombCat
爆炸猫游戏模拟器 - 人机对战版

规则说明：
1. 初始手牌8张，其中1张必为拆除卡
2. 抽到炸弹猫时必须使用拆除卡才能存活，否则立即死亡
3. 攻击卡可使对手连续执行多个回合，跳过卡可跳过当前回合
4. 牌堆用完后会使用弃牌堆重新洗牌

扩展说明：
1. 新增卡牌步骤：
   a. 创建继承自Card的子类
   b. 在Deck._initialize_cards中添加卡牌数量
   c. 在卡牌类中实现use方法处理效果
2. 注意维护deck和discard_pile的正确状态
"""
import random
import os
from time import sleep

# 设置随机种子以便于调试
# random.seed(42)

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
        print(f"🔥 {player.name} 发动攻击！{target.name} 将要连续行动 {game.remaining_turns + 1} 回合")
        game.remaining_turns += 2  # 在当前回合基础上加2个回合，因为原有的回合会在handle_turn结束后减掉
        game.current_player = target
        game.end_turn = True

class SkipCard(Card):
    """跳过卡"""

    def __init__(self):
        super().__init__("跳过", "跳过当前回合的抽牌阶段")

    def use(self, game, player, target):
        print(f"⏭️ {player.name} 跳过了回合")
        game.skip_draw = True
        game.end_turn = True

class ShuffleCard(Card):
    """洗牌卡"""

    def __init__(self):
        super().__init__("洗牌", "重新洗牌整个牌堆")

    def use(self, game, player, target):
        print("🃏 牌堆被重新洗牌！")
        game.deck.shuffle()


class SeeFutureCard(Card):
    """预见未来卡"""

    def __init__(self):
        super().__init__("预见未来", "查看牌堆顶的3张牌")

    def use(self, game, player, target):
        top_count = min(len(game.deck.cards), 3)
        top_cards = list(reversed(game.deck.cards[-top_count:]))
        print(f"🔮 {player.name} 查看了牌堆顶的{top_count}张牌")

        # 只展示给玩家，不展示给AI
        if not player.is_ai:
            cards_info = [f"{i + 1}. {card.name}" for i, card in enumerate(top_cards)]
            print("牌堆顶的牌（从上到下）:")
            for info in cards_info:
                print(info)
        else:
            # AI逻辑：记录牌堆顶部的情况
            if isinstance(top_cards[0], BombCatCard):
                # 如果顶部是炸弹猫，标记此信息
                game.ai_knows_bomb_on_top = True
                print("🤖 现在AI知道牌堆顶有炸弹猫！（测试信息）")  # 测试信息

class AlterFutureCard(Card):
    """改变未来卡"""

    def __init__(self):
        super().__init__("改变未来", "查看并排序牌堆顶的3张牌")

    def use(self, game, player, target):
        top_count = min(len(game.deck.cards), 3)
        top_cards = list(reversed(game.deck.cards[-top_count:]))
        game.deck.cards = game.deck.cards[:-top_count]  # 移除这些牌

        print(f"🔄 {player.name} 正在重新排列牌堆顶的{top_count}张牌")

        if player.is_ai:
            # AI逻辑：将爆炸猫（如果有）放在第2张位置
            bomb_cats = [i for i, card in enumerate(top_cards) if isinstance(card, BombCatCard)]
            if bomb_cats and top_count > 1:
                # 如果有爆炸猫，将其放在第二个位置（如果牌数足够）
                bomb_idx = bomb_cats[0]
                if top_count >= 2:
                    top_cards[bomb_idx], top_cards[-2] = top_cards[-2], top_cards[bomb_idx]
                    print("🤖 AI重新排列了牌堆顶的牌")
            # 将排序后的牌放回牌堆
            for card in top_cards:  # 倒序添加以保持原先的顺序
                game.deck.cards.append(card)
        else:
            # 玩家逻辑：显示卡牌并允许玩家重新排序
            cards_info = [f"{i + 1}. {card.name}" for i, card in enumerate(top_cards)]
            print("牌堆顶的牌（从上到下）:")
            for info in cards_info:
                print(info)

            # 让玩家选择排序
            print("请输入新的顺序，用空格间隔（例如：3 1 2 表示将第3张放在最上面，第1张中间，第2张最下面）")
            while True:
                try:
                    order = input("> ").strip().split()
                    if len(order) != top_count:
                        print(f"请输入{top_count}个数字")
                        continue

                    indices = [int(x) - 1 for x in order]
                    if any(i < 0 or i >= top_count for i in indices) or len(set(indices)) != top_count:
                        print("输入无效，请重新输入")
                        continue

                    # 根据玩家的输入重新排序
                    reordered = [top_cards[i] for i in indices]
                    # 将排序后的牌放回牌堆
                    for card in reversed(reordered):  # 倒序添加以保持玩家指定的顺序
                        game.deck.cards.append(card)
                    break
                except (ValueError, IndexError):
                    print("输入格式错误，请重新输入")

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
        ]
        self.cards = cards

    def shuffle(self):
        """洗牌操作"""
        random.shuffle(self.cards)

    def draw(self, num=1, refuse=None):
        """抽牌操作"""
        drawn = []
        for _ in range(num):
            if not self.cards:
                self.refill_from_discard()
            if self.cards:
                if refuse:
                    for card in self.cards:
                        if not any(isinstance(card, type(r)) for r in refuse):
                            # print(f"抽到 {card.name} 测试")  # 测试！
                            drawn.append(card)
                            self.cards.remove(card)
                            break
                else:
                    drawn.append(self.cards.pop())
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
            return [c for c in self.hand if isinstance(c, (SkipCard, AttackCard, ShuffleCard, AlterFutureCard))]
        else:
            return [c for c in self.hand if isinstance(c, card_type)]

    def draw_card(self, deck):
        """抽牌逻辑处理"""
        if drawn := deck.draw(1):
            card = drawn[0]
            if isinstance(card, BombCatCard):
                self.handle_bomb_cat(card, deck)
            else:
                self.hand.append(card)
                print(f"{self.name} 抽到了 {card.name}")

    def handle_bomb_cat(self, bomb_card, deck):
        """处理炸弹猫逻辑"""
        print(f"💣 {self.name} 抽到了炸弹猫！")
        if self.has_defuse():
            print("🛠️ 使用拆除卡...")
            defuse_card = next(c for c in self.hand if isinstance(c, DefuseCard))
            self.hand.remove(defuse_card)
            deck.discard_pile.append(defuse_card)

            # 选择放回位置
            if self.is_ai:
                pos = random.randint(0, len(deck.cards))
                print(f"🤖 将炸弹猫放回第 {pos} 位")
            else:
                pos = int(input(f"将炸弹猫放回的位置 (0-{len(deck.cards)})："))
            deck.insert_card(bomb_card, pos)
        else:
            print(f"💥 {self.name} 没有拆除卡！")
            self.alive = False


class Game:
    """游戏控制器"""

    def __init__(self):
        self.deck = Deck()
        self.player = Player("玩家")
        self.ai = Player("AI", is_ai=True)
        self._init_hands()
        self.current_player = self.player
        self.remaining_turns = 1
        self.skip_draw = False
        self.end_turn = False
        self.ai_knows_bomb_on_top = False

    def _init_hands(self):
        """初始化玩家手牌"""
        for p in [self.player, self.ai]:
            # 强制加入一张拆除卡
            defuse = next(c for c in self.deck.cards if isinstance(c, DefuseCard))
            self.deck.cards.remove(defuse)
            p.hand.append(defuse)
            # 抽7张牌
            p.hand.extend(self.deck.draw(7, refuse=[BombCatCard()]))

    def start(self):
        """游戏主循环"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("游戏开始！")
        while all([self.player.alive, self.ai.alive]):
            current = self.current_player
            other = self.ai if current == self.player else self.player

            print(f"\n=== {current.name} 的回合 ===")
            print(f"当前牌堆: {len(self.deck.cards)}张")
            print(f"手牌: {[c.name for c in current.hand]}")

            print(f"下面开始 {current.name} 的回合，算上本回合还有 {self.remaining_turns} 个回合")
            self.handle_turn(current)

            # 处理回合切换逻辑
            if self.remaining_turns > 0:
                self.remaining_turns -= 1
                if self.remaining_turns == 0:
                    self.current_player = other
                    self.remaining_turns = 1
            else:
                self.current_player = other

            # 重置状态
            self.skip_draw = False
            self.end_turn = False
            self.ai_knows_bomb_on_top = False

            sleep(0.5)  # 每次回合更换延时0.5秒

        print("\n=== 游戏结束 ===")
        print("胜者: AI" if self.ai.alive
              else "胜者: 玩家" if self.player.alive
              else "无人胜利")

    def handle_turn(self, player):
        """处理单个回合"""
        # AI逻辑
        if player.is_ai:
            while True:
                if self.ai_knows_bomb_on_top:  # 如果AI知道牌堆顶有炸弹猫，优先使用防御卡牌
                    cards = player.get_specific_cards('defensive')
                    action = 'play' if cards else 'draw'
                    self.ai_knows_bomb_on_top = False  # 用完后重置状态
                else:  # 否则AI随机选择
                    cards = player.get_specific_cards('playable')
                    action = random.choice(['play', 'draw']) if cards else 'draw'

                if action == 'play':
                    card = random.choice(cards)
                    print(f"🤖 使用 {card.name}")
                    card.use(self, player, self.get_other(player))
                    player.hand.remove(card)
                    self.deck.discard_pile.append(card)
                    if self.end_turn:
                        self.end_turn = False
                        break
                elif action == 'draw':  # 抽牌
                    print("🤖 选择抽牌")
                    player.draw_card(self.deck)
                    break

        # 玩家逻辑
        else:
            while True:
                action = input("请选择：1)出牌 2)抽牌\n> ").lower()
                cards = player.get_specific_cards('playable')
                if action == '2' or not cards:
                    if action == '1':
                        print("没有可出的卡牌, 请抽牌")
                    player.draw_card(self.deck)
                    break
                elif action == '1':
                    self.play_card_menu(player)
                    if self.end_turn:
                        self.end_turn = False
                        break
                else:
                    print("无效输入")

    def play_card_menu(self, player):
        """玩家出牌菜单"""
        playable = player.get_specific_cards('playable')
        for i, card in enumerate(playable):
            print(f"{i + 1}. {card.name}: {card.description}")

        while True:
            choice = input("选择卡牌编号 (0取消): ")
            if choice == '0':
                return
            if choice.isdigit() and 0 < int(choice) <= len(playable):
                card = playable[int(choice) - 1]
                card.use(self, player, self.get_other(player))
                player.hand.remove(card)
                self.deck.discard_pile.append(card)
                return
            print("无效选择")

    def get_other(self, player):
        """获取对手实例"""
        return self.ai if player == self.player else self.player

if __name__ == "__main__":
    while True:
        Game().start()
        restart = input("是否要重新开始？(y/n): ").lower()
        if restart != 'y':
            print("感谢游玩，再见！")
            break
