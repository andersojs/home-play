
def humanbytes(B: int):
    """Return the given bytes as a human friendly KB, MB, GB, or TB string"""
    # from https://stackoverflow.com/questions/12523586/python-format-size-application-converting-b-to-kb-mb-gb-tb
    B = float(B)
    KB = float(1024)
    MB = float(KB ** 2) # 1,048,576
    GB = float(KB ** 3) # 1,073,741,824
    TB = float(KB ** 4) # 1,099,511,627,776

    if B < KB:
        return '{0} {1}'.format(B,'Bytes' if 0 == B > 1 else 'Byte')
    elif KB <= B < MB:
        return '{0:.2f} KB'.format(B/KB)
    elif MB <= B < GB:
        return '{0:.2f} MB'.format(B/MB)
    elif GB <= B < TB:
        return '{0:.2f} GB'.format(B/GB)
    elif TB <= B:
        return '{0:.2f} TB'.format(B/TB)


# based on https://stackoverflow.com/a/42865957/2002471
units = {"B": 1, "KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40, "K": 2**10, "M": 2**20, "G": 2**30, "T": 2**40}

def parse_size(size):
    size = size.upper()
    #print("parsing size ", size)
    if not re.match(r' ', size):
        size = re.sub(r'([KMGT]?B?)', r' \1', size)
    number, unit = [string.strip() for string in size.split()]
    return int(float(number)*units[unit])