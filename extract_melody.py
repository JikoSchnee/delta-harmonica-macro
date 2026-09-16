import argparse
from pathlib import Path


SOURCE = Path("/Users/jikoschnee/Downloads/Sacred Play Secret Place（钢琴版）M_爱给网_aigei_com.mid")
DEST = Path("/Users/jikoschnee/Documents/ChatGPT/temp/delta-harmonica-macro/Sacred Play Secret Place（主旋律）.mid")


def read_u16(data, at):
    return int.from_bytes(data[at:at + 2], "big")


def read_u32(data, at):
    return int.from_bytes(data[at:at + 4], "big")


def read_vlq(data, at):
    value = 0
    while True:
        byte = data[at]
        at += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, at


def write_vlq(value):
    result = bytearray([value & 0x7F])
    value >>= 7
    while value:
        result.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(result)


def parse_notes(data):
    division = read_u16(data, 12)
    track_at = 14
    tracks = []
    notes = []

    for track_index in range(read_u16(data, 10)):
        if data[track_at:track_at + 4] != b"MTrk":
            raise ValueError(f"Invalid MIDI track at {track_at}")
        length = read_u32(data, track_at + 4)
        start = track_at + 8
        end = start + length
        tracks.append(data[track_at:end])
        at = start
        tick = 0
        running_status = None
        active = {}

        while at < end:
            delta, at = read_vlq(data, at)
            tick += delta
            status = data[at]
            if status < 0x80:
                if running_status is None:
                    raise ValueError("Running status used before a MIDI status byte")
                status = running_status
            else:
                at += 1

            if status == 0xFF:
                meta_type = data[at]
                at += 1
                size, at = read_vlq(data, at)
                at += size
                if meta_type == 0x2F:
                    break
                continue
            if status in (0xF0, 0xF7):
                size, at = read_vlq(data, at)
                at += size
                continue

            message_type = status >> 4
            channel = status & 0x0F
            if status < 0xF0:
                running_status = status
            size = 1 if message_type in (0xC, 0xD) else 2
            first = data[at]
            second = data[at + 1] if size == 2 else 0
            at += size

            if message_type not in (0x8, 0x9):
                continue
            key = (channel, first)
            if message_type == 0x9 and second:
                active[key] = (tick, second)
            else:
                started = active.pop(key, None)
                if started:
                    notes.append((started[0], tick, first, started[1], channel))

        track_at = end

    return division, tracks, notes


def extract_main_voice(notes, onset_window_ticks=100):
    notes.sort(key=lambda item: (item[0], item[2]))

    # Rolled chords in this file are struck within roughly 100 ticks. In a
    # rolled chord, the melody is the shorter, highest note; long low notes
    # are accompaniment. Single attacks are retained as melody candidates.
    attacks = []
    current = []
    previous_start = None
    for note in notes:
        if previous_start is None or note[0] - previous_start <= onset_window_ticks:
            current.append(note)
        else:
            attacks.append(current)
            current = [note]
        previous_start = note[0]
    if current:
        attacks.append(current)

    candidates = []
    for attack in attacks:
        if len(attack) == 1:
            chosen = attack[0]
            if chosen[1] - chosen[0] >= 50:
                candidates.append(chosen)
            continue

        short_notes = [note for note in attack if 50 <= note[1] - note[0] <= 1150]
        if short_notes:
            candidates.append(max(short_notes, key=lambda note: note[2]))

    # Remove low-register bass/grace notes and keep the uppermost active line
    # when the piano texture overlaps the next melodic attack.
    candidates = [note for note in candidates if note[2] >= 55 and note[1] - note[0] >= 50]
    candidates.sort(key=lambda item: (item[0], item[2]))
    melody = []
    for candidate in candidates:
        start, end, pitch, velocity, channel = candidate
        if melody and start < melody[-1][1]:
            if pitch <= melody[-1][2]:
                continue
            old = melody[-1]
            melody[-1] = (old[0], start, old[2], old[3], old[4])
        if end > start:
            melody.append((start, end, pitch, velocity, channel))
    return melody


def build_track(melody, onset_window_ticks):
    events = []
    for start, end, pitch, velocity, channel in melody:
        events.append((start, 1, bytes((0x90 | channel, pitch, velocity))))
        events.append((end, 0, bytes((0x80 | channel, pitch, 0))))
    events.sort(key=lambda event: (event[0], event[1]))

    body = bytearray()
    track_name = f"Main Melody (window {onset_window_ticks} ticks)".encode("ascii")
    body.extend(b"\x00\xFF\x03" + write_vlq(len(track_name)) + track_name)
    info = f"Close starts within {onset_window_ticks} ticks: keep highest pitch".encode("ascii")
    body.extend(b"\x00\xFF\x01" + write_vlq(len(info)) + info)
    last_tick = 0
    for tick, _, message in events:
        body.extend(write_vlq(tick - last_tick))
        body.extend(message)
        last_tick = tick
    body.extend(b"\x00\xFF\x2F\x00")
    return b"MTrk" + len(body).to_bytes(4, "big") + body


def main():
    parser = argparse.ArgumentParser(description="Extract the upper melody voice from a piano MIDI")
    parser.add_argument(
        "--onset-window-ticks",
        type=int,
        default=100,
        help="Group note starts within this many MIDI ticks and keep the highest pitch (default: 100)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEST,
        help="Output MIDI path",
    )
    args = parser.parse_args()
    if args.onset_window_ticks < 0:
        parser.error("--onset-window-ticks must be non-negative")

    source_data = SOURCE.read_bytes()
    division, tracks, notes = parse_notes(source_data)
    melody = extract_main_voice(notes, args.onset_window_ticks)
    header = b"MThd" + (6).to_bytes(4, "big") + (1).to_bytes(2, "big") + (2).to_bytes(2, "big") + division.to_bytes(2, "big")
    args.output.write_bytes(header + tracks[0] + build_track(melody, args.onset_window_ticks))
    print(f"wrote {args.output}")
    print(f"source notes: {len(notes)}; extracted notes: {len(melody)}; division: {division}")
    print(f"range: {min(note[2] for note in melody)}-{max(note[2] for note in melody)}")


if __name__ == "__main__":
    main()
