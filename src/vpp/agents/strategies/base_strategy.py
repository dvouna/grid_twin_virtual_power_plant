from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """
    Abstract base class for Grid Agent strategies.
    """
    @abstractmethod
    def evaluate(self, grid_status: str, prediction: str, fs_status: str) -> list:
        """
        Analyzes data and returns a list of tool-execution plans.
        """
        pass
