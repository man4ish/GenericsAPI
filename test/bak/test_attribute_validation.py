import unittest

import pandas as pd

from GenericsAPI.Utils import AttributeValidation


class AttributeUtilsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chem_vals = ['', 'foo bar', '1.0', 'InChIKey=JGHSBPIZNUXPLA-UHFFFAOYSA-N',
                         'JGHSBPIZNUXPLA-UHFFFAOYSA-N', 'N[C@@H](C)C(=O)O', 'C6H7O6Cl',
                         '1S/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1',
                         'InChI=1/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1']

    def test_mass(self):
        test_vals = ["", "1.0", "-1.0", "0.0", "foo"]
        expected = ["The following values are not floats: ['foo']",
                    "The following values are not positive values: ['-1.0', '0.0']"]
        warnings = AttributeValidation.mass(pd.Series(test_vals))
        self.assertCountEqual(warnings, expected)

    def test_smiles(self):
        # It's hard to write a strict Regex parser for SMILES
        expected = ['foo bar is not a valid smiles for instance 1',
                    '1.0 is not a valid smiles for instance 2',
                    '1S/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1 is not a'
                    ' valid smiles for instance 7',
                    'InChI=1/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1 is'
                    ' not a valid smiles for instance 8']
        warnings = AttributeValidation.smiles(pd.Series(self.chem_vals))
        self.assertCountEqual(warnings, expected)

    def test_formula(self):
        expected = ['foo bar is not a valid formula for instance 1',
                    '1.0 is not a valid formula for instance 2',
                    'InChIKey=JGHSBPIZNUXPLA-UHFFFAOYSA-N is not a valid formula for instance 3',
                    'JGHSBPIZNUXPLA-UHFFFAOYSA-N is not a valid formula for instance 4',
                    'N[C@@H](C)C(=O)O is not a valid formula for instance 5',
                    '1S/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1 is not a '
                    'valid formula for instance 7',
                    'InChI=1/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1 is '
                    'not a valid formula for instance 8']
        warnings = AttributeValidation.formula(pd.Series(self.chem_vals))
        self.assertCountEqual(warnings, expected)

    def test_inchi(self):
        expected = ['foo bar is not a valid inchi for instance 1',
                    '1.0 is not a valid inchi for instance 2',
                    'InChIKey=JGHSBPIZNUXPLA-UHFFFAOYSA-N is not a valid inchi for instance 3',
                    'JGHSBPIZNUXPLA-UHFFFAOYSA-N is not a valid inchi for instance 4',
                    'N[C@@H](C)C(=O)O is not a valid inchi for instance 5',
                    'C6H7O6Cl is not a valid inchi for instance 6']
        warnings = AttributeValidation.inchi(pd.Series(self.chem_vals))
        self.assertCountEqual(warnings, expected)

    def test_inchikey(self):

        expected = ['foo bar is not a valid inchi for instance 1',
                    '1.0 is not a valid inchi for instance 2',
                    'N[C@@H](C)C(=O)O is not a valid inchi for instance 5',
                    'C6H7O6Cl is not a valid inchi for instance 6',
                    '1S/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1 is not a '
                    'valid inchi for instance 7',
                    'InChI=1/C6H8O6/c7-1-2(8)5-3(9)4(10)6(11)12-5/h2,5,7-10H,1H2/t2-,5+/m0/s1 is '
                    'not a valid inchi for instance 8']
        warnings = AttributeValidation.inchikey(pd.Series(self.chem_vals))
        self.assertCountEqual(warnings, expected)