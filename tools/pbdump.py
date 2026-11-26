import sys, struct
def varint(b, i):
    r=0; s=0
    while True:
        c=b[i]; i+=1; r|=(c&0x7f)<<s; s+=7
        if not c&0x80: return r,i
def dump(b, depth=0, maxd=6):
    i=0; out=[]
    while i < len(b):
        try:
            key,i=varint(b,i)
        except IndexError:
            return False
        fn, wt = key>>3, key&7
        if fn==0: return False
        pad='  '*depth
        if wt==0:
            v,i=varint(b,i); print(f"{pad}{fn}: varint {v}")
        elif wt==1:
            if i+8>len(b): return False
            v=struct.unpack('<d',b[i:i+8])[0]; q=struct.unpack('<q',b[i:i+8])[0]; i+=8; print(f"{pad}{fn}: fixed64 dbl={v!r} int={q}")
        elif wt==5:
            if i+4>len(b): return False
            v=struct.unpack('<f',b[i:i+4])[0]; q=struct.unpack('<i',b[i:i+4])[0]; i+=4; print(f"{pad}{fn}: fixed32 flt={v!r} int={q}")
        elif wt==2:
            L,i=varint(b,i)
            if i+L>len(b): return False
            sub=b[i:i+L]; i+=L
            printable = all(32<=c<127 for c in sub) and L>0
            if printable: print(f"{pad}{fn}: str {sub.decode()!r}")
            else:
                print(f"{pad}{fn}: bytes[{L}] {{")
                import io, contextlib
                buf=io.StringIO()
                with contextlib.redirect_stdout(buf): ok=dump(sub, depth+1) if depth<maxd else False
                if ok is not False: sys.stdout.write(buf.getvalue())
                else: print(f"{pad}  raw {sub.hex()[:120]}")
                print(f"{pad}}}")
        else:
            return False
    return True
data=open(sys.argv[1],'rb').read()
sizes=[int(x) for x in sys.argv[2].split(',')]
off=0
for k,sz in enumerate(sizes):
    pkt=data[off:off+sz]; off+=sz
    if k in (0,1,len(sizes)-1):
        print(f"--- packet {k} size {sz}"); dump(pkt)
