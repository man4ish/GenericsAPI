import re


def _positive_float(values):  #check for floats and positive

    warnings = []
    not_float = []
    not_pos = []
    for val in values:
        if val == "":
            continue
        try:
            if float(val) <= 0:
                not_pos.append(val)
        except ValueError:
            not_float.append(val)
    if not_float:
        warnings.append(f"The following values are not floats: {not_float}")
    if not_pos:
        warnings.append(f"The following values are not positive values: {not_pos}")
    return warnings


def formula(values):    #check formuala
    re_exp = re.compile('^([0-9A-z])+$')
    return [f"{v} is not a valid formula for instance {i}" for i, v in values.iteritems()
            if v != "" and not re_exp.match(v)]


def inchi(values):   #check Inchies
    re_exp = re.compile('^(InChI=)?1S?\/([0-9A-z])+\/([0-9Ha-z+\-\(\)\\\/,])+$')
    return [f"{v} is not a valid inchi for instance {i}" for i, v in values.iteritems()
            if v != "" and not re_exp.match(v)]


def inchikey(values):   #check Inchkey
    re_exp = re.compile('^(InChIKey=)?[A-Z]{14}-[A-Z]{10}-[A-Z]$')
    return [f"{v} is not a valid inchi for instance {i}" for i, v in values.iteritems()
            if v != "" and not re_exp.match(v)]


def mass(values):  
    return _positive_float(values)


def smiles(values):  #check smiles
    re_exp = re.compile('^[A-z0-9@+\-\[\]\(\)\\\/%=#$]+$')
    return [f"{v} is not a valid smiles for instance {i}" for i, v in values.iteritems()
            if v != "" and not re_exp.match(v)]
