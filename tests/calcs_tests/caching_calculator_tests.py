import unittest
from calcs.caching_calculator import CachingCalculator, InvalidCalculatorSpecification

class TestCachingCalculator(unittest.TestCase):
    def test_simple_example(self):
        class ExampleCachingCalculator(CachingCalculator):
            __parameters__ = [ 'a', 'b' ]

            def __init__(self):
                self.reset()

            def reset(self):
                self._calculated = list()

            def calculated(self, name=None):
                if name:
                    self._calculated.append(name)
                return self._calculated

            def calculate_c(self):
                val = self.a * 2
                self.calculated('c')
                return val

            def calculate_d(self):
                val = self.b * 2
                self.calculated('d')
                return val

            def calculate_e(self):
                val = self.c + self.d
                self.calculated('e')
                return val

        # just setting a and b does *not* trigger calculation
        calc = ExampleCachingCalculator()
        calc.a = 5
        calc.b = 7
        self.assertEqual([], calc.calculated())

        # requesting e triggers all necessary calculations and produces the
        # correct cascaded result
        self.assertEqual(24, calc.e)
        self.assertEqual(['c', 'd', 'e'], calc.calculated())

        # just setting b does *not* trigger calculation
        calc.reset()
        calc.b = 3
        self.assertEqual([], calc.calculated())

        # but it does invalidate the cache, allowing recalculation of the new
        # correct result
        self.assertEqual(16, calc.e)

        # but notice only those calculations dependent on b were recalculated
        self.assertEqual(['d', 'e'], calc.calculated())

    def test_inter_object_example(self):
        class ExampleCachingCalculator(CachingCalculator):
            def __init__(self, calculations):
                self._calculated = calculations

            def reset(self, calculations):
                self._calculated = calculations

            def calculated(self, name):
                self._calculated.append((self, name))

        class ExampleCachingCalculatorA(ExampleCachingCalculator):
            __parameters__ = [ 'a' ]

            def __init__(self, other, calculations):
                super(ExampleCachingCalculatorA, self).__init__(calculations)
                self.other = other

            def calculate_c(self):
                val = self.a * 2
                self.calculated('c')
                return val

            def calculate_e(self):
                val = self.c + self.other.d
                self.calculated('e')
                return val

        class ExampleCachingCalculatorB(ExampleCachingCalculator):
            __parameters__ = [ 'b' ]

            def __init__(self, calculations):
                super(ExampleCachingCalculatorB, self).__init__(calculations)

            def calculate_d(self):
                val = self.b * 2
                self.calculated('d')
                return val

        # just setting a and b does *not* trigger calculation
        calculated = list()
        calcB = ExampleCachingCalculatorB(calculated)
        calcA = ExampleCachingCalculatorA(calcB, calculated)
        calcA.a = 5
        calcB.b = 7
        self.assertEqual([], calculated)

        # requesting e triggers all necessary calculations and produces the
        # correct cascaded result
        self.assertEqual(24, calcA.e)
        self.assertEqual([(calcA, 'c'), (calcB, 'd'), (calcA, 'e')], calculated)

        # just setting b does *not* trigger calculation
        del calculated[:]
        calcB.b = 3
        self.assertEqual([], calculated)

        # but it does invalidate the cache, allowing recalculation of the new
        # correct result
        self.assertEqual(16, calcA.e)

        # but notice only those calculations dependent on b were recalculated
        self.assertEqual([(calcB, 'd'), (calcA, 'e')], calculated)
