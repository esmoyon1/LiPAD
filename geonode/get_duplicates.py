from geonode.layers.models import Layer

def list_duplicate_layer():
    dups = []
    for x in Layer.objects.filter(name__icontains='fh'):
        if x.typename.split('_')[-1] is int:
            dups.append(x)
    with open('duplicatelayers.txt','w') as f:
        f.write('\n'.join(dups))
    return dups
