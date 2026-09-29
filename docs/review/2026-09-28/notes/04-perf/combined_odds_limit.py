"""Where combined_odds() stops working: the product quantized to 2 dp needs <= 28 digits."""
import sys
from decimal import Decimal, InvalidOperation
sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")
from src.services.coupon import combined_odds

for legs in (12, 15, 20, 30, 40, 50):
    ok_max = None
    for cents in range(101, 2001):  # every leg at the same price 1.01 .. 20.00
        price = Decimal(cents) / 100
        try:
            combined_odds([price] * legs)
            ok_max = price
        except InvalidOperation:
            print(f"{legs:2d} legs: fails from every leg at {price} (last ok {ok_max}); "
                  f"product ~ {float(price) ** legs:.2e}")
            break
    else:
        print(f"{legs:2d} legs: ok up to every leg at 20.00")
