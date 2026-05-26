from dataclasses import dataclass


@dataclass(slots=True)
class WalkForwardWindow:
    train_years: int
    test_years: int


class WalkForwardPlanner:
    def build(self, train_years: int = 3, test_years: int = 1) -> WalkForwardWindow:
        return WalkForwardWindow(train_years=train_years, test_years=test_years)
