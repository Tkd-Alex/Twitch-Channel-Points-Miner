import copy
from enum import Enum, auto
from random import uniform

from millify import millify

from TwitchChannelPointsMiner.utils import char_decision_as_index, float_round


class Strategy(Enum):
    MOST_VOTED = auto()
    HIGH_ODDS = auto()
    SMART_HIGH_ODDS = auto()
    PERCENTAGE = auto()
    SMART = auto()

    def __str__(self):
        return self.name


class Condition(Enum):
    GT = auto()
    LT = auto()
    GTE = auto()
    LTE = auto()

    def __str__(self):
        return self.name


class OutcomeKeys(object):
    # Real key on Bet dict ['']
    PERCENTAGE_USERS = "percentage_users"
    ODDS_PERCENTAGE = "odds_percentage"
    ODDS = "odds"
    TOP_POINTS = "top_points"
    # Real key on Bet dict [''] - Sum()
    TOTAL_USERS = "total_users"
    TOTAL_POINTS = "total_points"
    # This key does not exist
    DECISION_USERS = "decision_users"
    DECISION_POINTS = "decision_points"


class DelayMode(Enum):
    FROM_START = auto()
    FROM_END = auto()
    PERCENTAGE = auto()

    def __str__(self):
        return self.name


class FilterCondition(object):
    __slots__ = [
        "by",
        "where",
        "value",
    ]

    def __init__(self, by=None, where=None, value=None, decision=None):
        self.by = by
        self.where = where
        self.value = value

    def __repr__(self):
        return f"FilterCondition(by={self.by.upper()}, where={self.where}, value={self.value})"


class BetSettings(object):
    __slots__ = [
        "strategy",
        "percentage",
        "percentage_gap",
        "max_points",
        "target_odd",
        "only_doubt",
        "stealth_mode",
        "filter_condition",
        "delay",
        "delay_mode",
    ]

    def __init__(
        self,
        strategy: Strategy = None,
        percentage: int = None,
        percentage_gap: int = None,
        max_points: int = None,
        target_odd: float = None,
        only_doubt: bool = None,
        stealth_mode: bool = None,
        filter_condition: FilterCondition = None,
        delay: float = None,
        delay_mode: DelayMode = None,
    ):
        self.strategy = strategy
        self.percentage = percentage
        self.percentage_gap = percentage_gap
        self.max_points = max_points
        self.target_odd = target_odd
        self.only_doubt = only_doubt
        self.stealth_mode = stealth_mode
        self.filter_condition = filter_condition
        self.delay = delay
        self.delay_mode = delay_mode

    def default(self):
        self.strategy = self.strategy if not None else Strategy.SMART
        self.percentage = self.percentage if not None else 5
        self.percentage_gap = self.percentage_gap if not None else 20
        self.max_points = self.max_points if not None else 50000
        self.target_odd = self.target_odd if not None else 3
        self.only_doubt = self.only_doubt if not None else False
        self.stealth_mode = self.stealth_mode if not None else False
        self.delay = self.delay if not None else 6
        self.delay_mode = self.delay_mode if not None else DelayMode.FROM_END

    def __repr__(self):
        return f"BetSettings(strategy={self.strategy}, percentage={self.percentage}, percentage_gap={self.percentage_gap}, max_points={self.max_points}, stealth_mode={self.stealth_mode})"


class Bet(object):
    __slots__ = ["outcomes", "decision", "total_users", "total_points", "settings"]

    def __init__(self, outcomes: list, settings: BetSettings):
        self.outcomes = outcomes
        self.__clear_outcomes()
        self.decision: dict = {}
        self.total_users = 0
        self.total_points = 0
        self.settings = settings

    def update_outcomes(self, outcomes):
        for index in range(0, len(self.outcomes)):
            self.outcomes[index][OutcomeKeys.TOTAL_USERS] = int(
                outcomes[index][OutcomeKeys.TOTAL_USERS]
            )
            self.outcomes[index][OutcomeKeys.TOTAL_POINTS] = int(
                outcomes[index][OutcomeKeys.TOTAL_POINTS]
            )
            if outcomes[index]["top_predictors"] != []:
                # Sort by points placed by other users
                outcomes[index]["top_predictors"] = sorted(
                    outcomes[index]["top_predictors"],
                    key=lambda x: x["points"],
                    reverse=True,
                )
                # Get the first elements (most placed)
                top_points = outcomes[index]["top_predictors"][0]["points"]
                self.outcomes[index][OutcomeKeys.TOP_POINTS] = top_points

        self.total_users = (
            self.outcomes[0][OutcomeKeys.TOTAL_USERS]
            + self.outcomes[1][OutcomeKeys.TOTAL_USERS]
        )
        self.total_points = (
            self.outcomes[0][OutcomeKeys.TOTAL_POINTS]
            + self.outcomes[1][OutcomeKeys.TOTAL_POINTS]
        )

        if (
            self.total_users > 0
            and self.outcomes[0][OutcomeKeys.TOTAL_POINTS] > 0
            and self.outcomes[1][OutcomeKeys.TOTAL_POINTS] > 0
        ):
            for index in range(0, len(self.outcomes)):
                self.outcomes[index][OutcomeKeys.PERCENTAGE_USERS] = float_round(
                    (100 * self.outcomes[index][OutcomeKeys.TOTAL_USERS])
                    / self.total_users
                )
                self.outcomes[index][OutcomeKeys.ODDS] = float_round(
                    self.total_points / self.outcomes[index][OutcomeKeys.TOTAL_POINTS]
                )
                self.outcomes[index][OutcomeKeys.ODDS_PERCENTAGE] = float_round(
                    100 / self.outcomes[index][OutcomeKeys.ODDS]
                )

        self.__clear_outcomes()

    def __repr__(self):
        return f"Bet(total_users={millify(self.total_users)}, total_points={millify(self.total_points)}), decision={self.decision})\n\t\tOutcome A({self.get_outcome(0)})\n\t\tOutcome B({self.get_outcome(1)})"

    def get_decision(self, parsed=False):
        decision = self.outcomes[0 if self.decision["choice"] == "A" else 1]
        return decision if parsed is False else Bet.__parse_outcome(decision)

    @staticmethod
    def __parse_outcome(outcome):
        return f"{outcome['title']} ({outcome['color']}), Points: {millify(outcome[OutcomeKeys.TOTAL_POINTS])}, Users: {millify(outcome[OutcomeKeys.TOTAL_USERS])} ({outcome[OutcomeKeys.PERCENTAGE_USERS]}%), Odds: {outcome[OutcomeKeys.ODDS]} ({outcome[OutcomeKeys.ODDS_PERCENTAGE]}%)"

    def get_outcome(self, index):
        return Bet.__parse_outcome(self.outcomes[index])

    def __clear_outcomes(self):
        for index in range(0, len(self.outcomes)):
            keys = copy.deepcopy(list(self.outcomes[index].keys()))
            for key in keys:
                if key not in [
                    OutcomeKeys.TOTAL_USERS,
                    OutcomeKeys.TOTAL_POINTS,
                    OutcomeKeys.TOP_POINTS,
                    OutcomeKeys.PERCENTAGE_USERS,
                    OutcomeKeys.ODDS,
                    OutcomeKeys.ODDS_PERCENTAGE,
                    "title",
                    "color",
                    "id",
                ]:
                    del self.outcomes[index][key]
            for key in [
                OutcomeKeys.PERCENTAGE_USERS,
                OutcomeKeys.ODDS,
                OutcomeKeys.ODDS_PERCENTAGE,
                OutcomeKeys.TOP_POINTS,
            ]:
                if key not in self.outcomes[index]:
                    self.outcomes[index][key] = 0

    def __return_choice(self, key) -> str:
        return "A" if self.outcomes[0][key] > self.outcomes[1][key] else "B"

    def skip(self) -> bool:
        if self.settings.filter_condition is not None:
            # key == by , condition == where
            key = self.settings.filter_condition.by
            condition = self.settings.filter_condition.where
            value = self.settings.filter_condition.value

            fixed_key = (
                key
                if key not in [OutcomeKeys.DECISION_USERS, OutcomeKeys.DECISION_POINTS]
                else key.replace("decision", "total")
            )
            if key in [OutcomeKeys.TOTAL_USERS, OutcomeKeys.TOTAL_POINTS]:
                compared_value = (
                    self.outcomes[0][fixed_key] + self.outcomes[1][fixed_key]
                )
            else:
                outcome_index = char_decision_as_index(self.decision["choice"])
                compared_value = self.outcomes[outcome_index][fixed_key]

            if self.settings.strategy == Strategy.SMART_HIGH_ODDS:
                if (
                    self.outcomes[0][OutcomeKeys.TOTAL_POINTS] > 0
                    and self.outcomes[1][OutcomeKeys.TOTAL_POINTS] == 0
                ):
                    return False, "No bet on B."
                if (
                    self.outcomes[0][OutcomeKeys.TOTAL_POINTS] == 0
                    and self.outcomes[1][OutcomeKeys.TOTAL_POINTS] > 0
                ):
                    if not self.settings.only_doubt:
                        return False, "No bet on A."
                both_odds_too_low = (
                    self.outcomes[0][OutcomeKeys.ODDS] <= self.settings.target_odd
                    and self.outcomes[1][OutcomeKeys.ODDS] <= self.settings.target_odd
                )
                is_only_doubt = (
                    self.outcomes[1][OutcomeKeys.ODDS] <= self.settings.target_odd
                    and self.settings.only_doubt
                )
                if both_odds_too_low:
                    output = "Odd is too low.\n"
                elif is_only_doubt:
                    output = "Odd is too low and only_doubt activated.\n"
                if both_odds_too_low or is_only_doubt:
                    output += f"{self.get_outcome(0)}\n{self.get_outcome(1)}\n"
                    output += f"Target odd: {self.settings.target_odd}"
                    return True, output  # Skip

            # Check if condition is satisfied
            if condition == Condition.GT:
                if compared_value > value:
                    return False, compared_value
            elif condition == Condition.LT:
                if compared_value < value:
                    return False, compared_value
            elif condition == Condition.GTE:
                if compared_value >= value:
                    return False, compared_value
            elif condition == Condition.LTE:
                if compared_value <= value:
                    return False, compared_value
            return True, compared_value  # Else skip the bet
        else:
            return False, 0  # Default don't skip the bet

    def calculate_sho_bet(self, index):
        low_odd_points = self.outcomes[1 - index][OutcomeKeys.TOTAL_POINTS]
        high_odd_points = self.outcomes[index][OutcomeKeys.TOTAL_POINTS]
        if high_odd_points <= 50:  # in case no one bet
            return 50
        else:
            target_odd = self.settings.target_odd
            if self.outcomes[index][OutcomeKeys.ODDS] > (target_odd * 2):
                # don't bet too much if odds is too high
                target_odd = self.outcomes[index][OutcomeKeys.ODDS] / 2
            return int((low_odd_points / (target_odd - 1)) - high_odd_points)

    def calculate(self, balance: int) -> dict:
        self.decision = {"choice": None, "amount": 0, "id": None}
        if self.settings.only_doubt:
            self.decision["choice"] = "B"
        elif self.settings.strategy == Strategy.MOST_VOTED:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.TOTAL_USERS)
        elif self.settings.strategy == Strategy.HIGH_ODDS:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.ODDS)
        elif self.settings.strategy == Strategy.SMART_HIGH_ODDS:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.ODDS)
        elif self.settings.strategy == Strategy.PERCENTAGE:
            self.decision["choice"] = self.__return_choice(OutcomeKeys.ODDS_PERCENTAGE)
        elif self.settings.strategy == Strategy.SMART:
            difference = abs(
                self.outcomes[0][OutcomeKeys.PERCENTAGE_USERS]
                - self.outcomes[1][OutcomeKeys.PERCENTAGE_USERS]
            )
            self.decision["choice"] = (
                self.__return_choice(OutcomeKeys.ODDS)
                if difference < self.settings.percentage_gap
                else self.__return_choice(OutcomeKeys.TOTAL_USERS)
            )

        if self.decision["choice"] is not None:
            index = char_decision_as_index(self.decision["choice"])
            self.decision["id"] = self.outcomes[index]["id"]
            if self.settings.strategy == Strategy.SMART_HIGH_ODDS:
                self.decision["amount"] = min(
                    self.calculate_sho_bet(index),
                    int(balance * (self.settings.percentage / 100)),
                    self.settings.max_points,
                )
            else:
                self.decision["amount"] = min(
                    int(balance * (self.settings.percentage / 100)),
                    self.settings.max_points,
                )
            if (
                self.settings.stealth_mode is True
                and self.decision["amount"]
                >= self.outcomes[index][OutcomeKeys.TOP_POINTS]
            ):
                reduce_amount = uniform(1, 5)
                self.decision["amount"] = (
                    self.outcomes[index][OutcomeKeys.TOP_POINTS] - reduce_amount
                )
            self.decision["amount"] = int(self.decision["amount"])
        return self.decision
