"""
Utility helpers for storing filament metadata on NTAG215 tags using
an NDEF Text record that carries a JSON payload.
Designed for MicroPython on Raspberry Pi Pico.
"""

import time
import ujson

NDEF_TLV = 0x03
TERMINATOR_TLV = 0xFE
START_PAGE = 4
MAX_PAGE = 134  # inclusive


def _encode_text_record(text, language="en"):
    text_bytes = text.encode("utf-8")
    lang_bytes = language.encode("ascii")
    if len(lang_bytes) > 0x3F:
        raise ValueError("Language code too long")
    status = len(lang_bytes) & 0x3F  # UTF-8 encoding flag cleared
    payload = bytes([status]) + lang_bytes + text_bytes
    if len(payload) > 0xFFFF:
        raise ValueError("Payload too large for NDEF record")

    header = 0xD1  # MB=1, ME=1, SR=1, TNF=0x1 (well-known)
    if len(payload) > 0xFF:
        header = 0xC1  # switch off short record flag for extended payload
    record = bytearray([header, 0x01])

    if len(payload) > 0xFF:
        record.extend(len(payload).to_bytes(4, "big"))
    else:
        record.append(len(payload))

    record.append(ord("T"))
    record.extend(payload)
    return bytes(record)


def _decode_text_record(message):
    print("DEBUG header:", hex(message[0]), "len:", len(message))

    if not message:
        return None
    header = message[0]
    short_record = (header & 0x10) == 0x10
    has_id = (header & 0x08) == 0x08
    if (header & 0x07) != 0x01:
        return None

    type_length = message[1]
    idx = 2
    if short_record:
        payload_length = message[idx]
        idx += 1
    else:
        payload_length = int.from_bytes(message[idx:idx+4], "big")
        idx += 4

    record_type = message[idx:idx + type_length]
    idx += type_length

    if has_id:
        if idx >= len(message):
            return None
        id_length = message[idx]
        idx += 1 + id_length

    if record_type != b"T":
        return None

    payload = message[idx:idx + payload_length]
    if not payload:
        return ""

    status = payload[0]
    lang_length = status & 0x3F
    text = payload[1 + lang_length:]
    return text.decode("utf-8")


def _encode_tlv(record_bytes):
    length = len(record_bytes)
    tlv = bytearray()
    tlv.append(NDEF_TLV)
    if length > 0xFE:
        tlv.append(0xFF)
        tlv.extend(length.to_bytes(2, "big"))
    else:
        tlv.append(length)
    tlv.extend(record_bytes)
    tlv.append(TERMINATOR_TLV)
    return tlv


def read_ndef_json(pn532, start_page=START_PAGE, max_pages=80):
    """Return JSON data stored in the first NDEF Text record or None."""
    print("DEBUG start_page:", start_page, "max_pages:", max_pages)
    raw = bytearray()
    end_page = min(MAX_PAGE, start_page + max_pages)
    for page in range(start_page, end_page + 1):
        block = pn532.ntag2xx_read_block(page)
        if block is None:
            break
        raw.extend(block)
        if TERMINATOR_TLV in block:
            break

    if not raw:
        print("DEBUG no raw data read")
        return None

    idx = 0
    length = len(raw)
    print("DEBUG total raw length:", length)
    while idx < length:
        tlv_type = raw[idx]
        if tlv_type == 0x00:
            idx += 1
            continue
        if tlv_type == TERMINATOR_TLV:
            break
        if idx + 1 >= length:
            break

        if tlv_type == NDEF_TLV:
            tlv_len = raw[idx + 1]
            idx += 2
            if tlv_len == 0xFF:
                if idx + 2 > length:
                    break
                tlv_len = (raw[idx] << 8) | raw[idx + 1]
                idx += 2
            message = raw[idx:idx + tlv_len]


            print("DEBUG raw TLV:", [hex(b) for b in raw[:32]])
            print("DEBUG message:", [hex(b) for b in message[:32]])



        text = _decode_text_record(message)
        if not text:
            return None

        # Strip padding / nulls / stray terminators at the end
        text = text.strip("\x00\xfe \r\n\t")

        try:
            return ujson.loads(text)
        except Exception as e:
            print("DEBUG raw text snippet:", text[:80])
            raise e

        else:
            tlv_len = raw[idx + 1]
            idx += 2 + tlv_len
    return None


def write_ndef_json(pn532, data, start_page=START_PAGE):
    """Write JSON data into the first NDEF Text record."""
    text = ujson.dumps(data)
    record = _encode_text_record(text)
    tlv = _encode_tlv(record)

    # Pad to 4-byte boundaries for NTAG writes.
    if len(tlv) % 4:
        padding = 4 - (len(tlv) % 4)
        tlv.extend(b"\x00" * padding)

    total_pages = len(tlv) // 4
    end_page = start_page + total_pages
    if end_page > MAX_PAGE + 1:
        raise ValueError("Data does not fit on tag")

    page = start_page
    offset = 0
    while offset < len(tlv):
        block = tlv[offset:offset + 4]
        success = pn532.ntag2xx_write_block(page, block)
        if not success:
            raise RuntimeError("Failed to write page {}".format(page))
        time.sleep_ms(5)
        page += 1
        offset += 4

    return total_pages

