from time import time


class Timer:
    def __init__(self):
        self.start = time()

    def done(self) -> str:
        return f"{time() - self.start:.2f}s"
