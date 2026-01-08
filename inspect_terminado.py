import terminado
from terminado.management import PtyWithClients
import inspect

print("Terminado version:", terminado.__version__)
print("\nUniqueTermManager methods:")
for m in dir(terminado.UniqueTermManager):
    if not m.startswith('_'):
        print(m)

print("\nPtyWithClients methods:")
for m in dir(PtyWithClients):
    if not m.startswith('_'):
        print(m)

print("\nPtyWithClients.on_read signature:")
try:
    print(inspect.signature(PtyWithClients.on_read))
except:
    print("Could not get signature")
