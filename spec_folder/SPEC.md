# Remeha EHC-16 BLE connector — spec (build in any language)

Reads live heat-pump data over BLE. Firmware-fixed (same for every EHC-16 and possible for other EHC devices); only
MAC + PIN differ per device so alwasy scan based on device name. Flow: scan→connect→bond(PIN)→enable notify→pre-auth→
STL session→read objects. All plaintext after the handshakes.

## GATT UUIDs
- REQ (write WITH response):   `496b1b03-cebc-4d59-9c32-14ea88c266f9`
- RSP (notify, STL responses): `ab9af948-fb86-492d-820d-bdea2dcb7ecf`
- PRE_TRIGGER (write):         `94e54dc4-f69a-4c0c-8a6f-cc8f3135c665`
- PRE_CHAL (notify):           `69092300-a182-4fea-803b-24ada406da8a`
- PRE_RESP (write):            `f1ca5aeb-02cd-44a8-972b-44b6e7250d0b`
- PRE_ACK (notify):            `e2c47825-6dff-4d79-b74a-5bdc4f4661cf`

MTU=23 (frames ≤20B). Bond = BLE passkey = 6-digit PIN on sticker. Enable notify
on RSP, PRE_CHAL, PRE_ACK. Writes to REQ must be write-WITH-response.

## TEA cipher (both handshakes; 8 bytes→8 bytes, no key)
K=0x15EFA43F, DELTA=0x9E3779B9, LEVEL=4. All math uint32 (& 0xFFFFFFFF), >> logical.
```
tea(c8, endian):
  v0=u32(c8[0:4],endian); v1=u32(c8[4:8],endian)
  a=b=LEVEL; s=DELTA; L=LEVEL
  repeat 32:
    a=(a+((K+((b<<4)&M))^(v0+(b>>5))^(b+s)))&M
    b=(b+((v1+((a<<4)&M))^(s+a)^(L+(a>>5))))&M
    s=(s+DELTA)&M
  return u32bytes(a,endian)+u32bytes(b,endian)
```
Test: tea("34294c40088aea6b",big)="ac7fe88bd97bf669".

## CRC-16/MODBUS (for request frames)
init=0xFFFF; per byte: crc^=byte; 8×: crc=(crc>>1)^0xA001 if crc&1 else crc>>1.
Append over frame-body (bytes after leading 0xFF), HIGH byte first.

## Handshakes (once per connection, in order)
Pre-auth: write `[]`→PRE_TRIGGER; get 8B chal on PRE_CHAL;
  write `04`++tea(chal,**little**) → PRE_RESP; get `01` on PRE_ACK.
STL: write `ff0102010002000323d6`→REQ; get notif on RSP, chal=notif[8:16];
  write `FF`+`01020100020203`+`FF04`+tea(chal,**big**)+crc → REQ; get ack;
  write `ff01020100000003ff582a00e544`→REQ; get ack. (reads before this → error `0203..35ff`)

## Read object(index,sub,element)
Request (14B): `FF 01 02 00 00 00 00 00 EL IDXHI IDXLO SUB CRChi CRClo`
  EL=element (1, or 0xFF scalar); IDX=big-endian; CRC over the 11 body bytes.
  e.g. 0x501d/0/1 → `ff0102000000000001501d006fab`. Write to REQ.
Response = notifications on RSP, reassemble:
  frame[0]<0xFF → fragment `[seq][payload]`, order by seq.
  frame[0]==0xFF → if fragments collected: terminator→concat payloads = msg;
                   else single-frame → msg = frame without leading 0xFF.
  msg = HEADER(11B) + DATA (+2B CRC only if single-frame).
  HEADER=`01 02 00 00 00 01 00 EL IDXHI IDXLO SUB`. VALIDATE HEADER[8:11]==your
  IDXHI,IDXLO,SUB (else stale reply → discard, keep reading).
Decode DATA: little-endian; width 1/2/4B (int16 for the 0x501d block). Divide by
scale. Null if value ∈ {-32768,-1,0xFFFF,0xFFFFFFFF} or bytes end `02 06`. Printable
ASCII = string (0x340f = "EHC-16").

## Data → see registers.json
0x501d sub0 el1 = 122B = 61 int16 monitoring values (offsets in registers.json).
Energy/counters = read each index directly (uint32 LE). Enums + scales in
registers.json. (Full enum lists & config descriptors: ../captures/*.json.)

## Gotchas
write-with-response; MTU≤20B/frame; validate response index; pre-auth=little,
STL=big endian; CRC hi-first; do BOTH handshakes; sentinels=null.
