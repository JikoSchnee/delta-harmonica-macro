const NOTE_KEYS = { "1": "z", "2": "x", "3": "c", "4": "v", "5": "b", "6": "n", "7": "m", "1'": "," };
const MAKE_CODES = { z: 44, x: 45, c: 46, v: 47, b: 48, n: 49, m: 50, ",": 51 };
const MOUSE_BUTTONS = { L: { name: "左键降调", ghub: 1, razer: 1 }, M: { name: "中键半音", ghub: 3, razer: 3 }, R: { name: "右键升调", ghub: 2, razer: 2 } };
// Leave a short release window between every pair of played notes.  A gap only
// between repeated notes works for a plain melody, but modifier changes (for
// example `#1'` -> `7` in 鸟之诗) otherwise release and press several mouse /
// keyboard inputs in the same driver tick.  Delta Force can then sample a
// stale modifier, or miss the key press altogether.
const INPUT_TRANSITION_GAP_MS = 18;
const MIN_NOTE_HOLD_MS = 24;
const PREVIEW_MIDI = { "1": 60, "2": 62, "3": 64, "4": 65, "5": 67, "6": 69, "7": 71, "1'": 72 };
const PREVIEW_OFFSETS = { L: -12, M: 1, R: 12 };
const KEY_TO_NOTE = { z: "1", x: "2", c: "3", v: "4", b: "5", n: "6", m: "7", ",": "1'" };
const KEYBOARD_MODIFIER_LABELS = { L: "左键", M: "中键", R: "右键" };
const KEYBOARD_LABEL_TO_MODIFIER = Object.fromEntries(Object.entries(KEYBOARD_MODIFIER_LABELS).map(([modifier, label]) => [label, modifier]));
const RECORD_BEATS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
const DIATONIC_MIDI = { "1": 60, "2": 62, "3": 64, "4": 65, "5": 67, "6": 69, "7": 71 };
const BUILTIN_SONG_LIBRARY = [
 { title: "鸟之诗", detail: "1=C · 4/4 · 122 BPM · MIDI 主旋律版", key: "1=C", meter: "4/4", bpm: 122, jianpu: ",7:0.96 0:0.04 #1:0.46 0:0.04 2:0.45999999999999996 0:0.04 6:0.475 0:0.025 |\n#4:0.96 0:0.04 #4:0.45999999999999996 0:0.04 3:0.21 0:0.04 #4:3.21 0:0.04 |\n3:0.46 0:0.04 #4:0.46 0:0.04 6:0.46 0:0.04 3:0.46 0:0.04 |\n#1:0.46 0:0.04 2:0.475 0:0.025 #1:0.9600000000000001 0:0.04 #1_ ,7:0.21 |\n0:0.04 #,4:2.25 0. ,7:0.975 0:0.025 #1:0.475 0:0.025 2:0.475 |\n0:0.025 6:0.45999999999999996 0:0.04 #4:0.96 0:0.04 #4_ 3:0.21 0:0.04 |\n#4:3.21 0:0.04 3:0.475 0:0.025 #4:0.475 0:0.025 6:0.475 0:0.025 |\n#4:0.475 0:0.025 6:0.46 0:0.04 2':0.475 0:0.025 #1':0.71 0:0.04 |\n7:0.71 0:0.04 #4:1.96 0:0.04 3:0.46 0:0.04 #4:0.975 0:0.025 |\n6:0.975 0:0.025 7:0.975 0:0.025 #1':0.975 0:0.025 #4:0.96 0:0.04 |\n#4:0.45999999999999996 0:0.04 3:0.21 0:0.04 #4:3.21 0:0.04 3:0.46 0:0.04 |\n#4:0.46 0:0.04 6:0.46 0:0.04 3:0.46 0:0.04 #1:0.46 0:0.04 |\n2:0.475 0:0.025 #1:0.9600000000000001 0:0.04 #1_ ,7:0.21 0:0.04 #,4:2.25 |\n0. ,7:0.975 0:0.025 #1:0.475 0:0.025 2:0.475 0:0.025 6:0.45999999999999996 |\n0:0.04 #4:0.96 0:0.04 #4_ 3:0.21 0:0.04 #4:3.21 0:0.04 |\n3:0.475 0:0.025 #4:0.475 0:0.025 6:0.475 0:0.025 #4:0.475 0:0.025 |\n6:0.46 0:0.04 2':0.475 0:0.025 #1':3.5 7:0.46 0:0.04 7:2.96 |\n0:0.04 7:0.9600000000000001 0:0.04 #1':3.475 0:0.025 7:0.46 0:0.04 7--- |\n0. #5:0.46 0:0.04 #5:0.7100000000000001 0:0.04 #5:0.725 0:0.025 #5:0.475 |\n0:0.025 #5:0.7100000000000001 0:0.04 #4:0.7100000000000001 0:0.04 #4:0.96 0:0.04 #5 |\n#6:0.46 0:0.04 7:0.71 0:0.04 #6:0.71 0:0.04 #5:0.9600000000000001 0:0.04 |\n#2:0.45999999999999996 0:0.04 #2:2.96 0:0.04 #1:0.96 0:0.04 ,7 0. |\n#5:0.46 0:0.04 #5:0.7100000000000001 0:0.04 #5:0.725 0:0.025 #5:0.475 0:0.025 |\n#5:0.7100000000000001 0:0.04 #4:0.7100000000000001 0:0.04 #4:0.96 0:0.04 #2:0.9600000000000001 0:0.04 |\n#4:0.45999999999999996 0:0.04 #5:0.725 0:0.025 #6:0.725 0:0.025 7:4.475 0:3.525 |\n#5:0.46 0:0.04 #5:0.7100000000000001 0:0.04 #5:0.725 0:0.025 #5:0.475 0:0.025 |\n#5:0.7100000000000001 0:0.04 #4:0.7100000000000001 0:0.04 #4:0.96 0:0.04 #5 #6:0.46 |\n0:0.04 7:0.71 0:0.04 #6:0.71 0:0.04 #5:0.9600000000000001 0:0.04 #2:0.45999999999999996 |\n0:0.04 #2:2.96 0:0.04 #1:0.96 0:0.04 ,7 0. #2:0.46 |\n0:0.04 #2:0.7100000000000001 0:0.04 #2:0.71 0:0.04 #2:0.46 0:0.04 #1:0.71 |\n0:0.04 #2:0.7100000000000001 0:0.04 #4:0.975 0:0.025 #2 #4:0.45999999999999996 0:0.04 |\n#5:1.96 0:0.04 7:0.9600000000000001 0:0.04 #6:0.96 0:0.04 #5:2.96 0:0.04 |\n#4:0.96 0:0.04 4:0.45999999999999996 0:0.04 4:0.45999999999999996 0:0.04 4:0.45999999999999996 0:0.04 |\n#2__ 4.. 0. 4:0.975 0:0.025 #4:0.975 0:0.025 #5:0.975 |\n0:0.025 #2:1.46 0:0.04 1:0.45999999999999996 0:0.04 1:3.46 0:0.04 1_ |\n#1:0.46 0:0.04 #2:1.46 0:0.04 4:0.45999999999999996 0:0.04 4:0.45999999999999996 0:0.04 |\n4:0.45999999999999996 0:0.04 #,6:0.225 0:0.025 4:5.21 0:0.04 #2:0.46 0:0.04 |\n#1:0.46 0:0.04 #2:0.975 0:0.025 #2:0.45999999999999996 0:0.04 #1:0.45999999999999996 0:0.04 |\n#2:0.45999999999999996 0:0.04 #5:0.96 0:0.04 #5:4.46 0:0.04 4:0.96 0:0.04 |\n4:0.46 0:0.04 #2:0.21000000000000002 0:0.04 4.. 0. 4:0.975 0:0.025 |\n#4:0.975 0:0.025 #5:0.975 0:0.025 #2:1.46 0:0.04 1:0.45999999999999996 0:0.04 |\n1:3.46 0:0.04 1_ #1:0.46 0:0.04 #2:1.46 0:0.04 #5:0.96 |\n0:0.04 #5:0.46 0:0.04 #4:0.21000000000000002 0:0.04 #5:5.21 0:0.04 #4:0.46 |\n0:0.04 3:0.46 0:0.04 #4:0.96 0:0.04 #4:0.45999999999999996 0:0.04 3_ |\n#4:0.475 0:0.025 #5:0.96 0:0.04 #5:1.96 0:0.04 ,7:0.96 0:0.04 |\n#1:0.46 0:0.04 2:0.45999999999999996 0:0.04 6:0.46 0:0.04 #4:0.96 0:0.04 |\n#4:0.45999999999999996 0:0.04 3:0.21 0:0.04 #4:3.21 0:0.04 3:0.46 0:0.04 |\n#4:0.46 0:0.04 6:0.46 0:0.04 3:0.46 0:0.04 #1:0.46 0:0.04 |\n2:0.475 0:0.025 #1:0.9600000000000001 0:0.04 #1_ ,7:0.21 0:0.04 #,4:2.25 |\n0. ,7:0.975 0:0.025 #1:0.475 0:0.025 2:0.475 0:0.025 6:0.45999999999999996 |\n0:0.04 #4:0.96 0:0.04 #4_ 3:0.21 0:0.04 #4:3.21 0:0.04 |\n3:0.475 0:0.025 #4:0.475 0:0.025 6:0.475 0:0.025 #4:0.475 0:0.025 |\n6:0.46 0:0.04 2':0.475 0:0.025 #1':0.71 0:0.04 7:0.71 0:0.04 |\n#4:1.96 0:0.04 3:0.46 0:0.04 #4:0.975 0:0.025 6:0.975 0:0.025 |\n7:0.975 0:0.025 #1':0.975 0:0.025 #4:0.96 0:0.04 #4:0.45999999999999996 0:0.04 |\n3:0.21 0:0.04 #4:3.21 0:0.04 3:0.46 0:0.04 #4:0.46 0:0.04 |\n6:0.46 0:0.04 3:0.46 0:0.04 #1:0.46 0:0.04 2:0.475 0:0.025 |\n#1:0.9600000000000001 0:0.04 #1_ ,7:0.21 0:0.04 #,4:2.25 0. ,7:0.975 |\n0:0.025 #1:0.475 0:0.025 2:0.475 0:0.025 6:0.45999999999999996 0:0.04 #4:0.96 |\n0:0.04 #4_ 3:0.21 0:0.04 #4:3.21 0:0.04 3:0.475 0:0.025 |\n#4:0.475 0:0.025 6:0.475 0:0.025 #4:0.475 0:0.025 6:0.46 0:0.04 |\n2':0.475 0:0.025 #1':3.5 7:0.46 0:0.04 7:2.96 0:0.04 7:0.9600000000000001 |\n0:0.04 #1':3.475 0:0.025 7:0.46 0:0.04 7:10 |" },
 { title: "天使爱美丽", detail: "1=G · 4/4 · 93 BPM · 双页图片校对版", bpm: 93, score: `0/0.5 1/0.25 7/0.25 1/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 1/0.25 7/0.5 1/0.25 2/0.25 1/2 |
0/0.5 7/0.25 6/0.25 7/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 6/0.25 7/1 0/2 |
0/0.5 1/0.25 7/0.25 1/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 1/0.25 7/0.5 1/0.25 2/0.25 1/2 |
0/0.5 7/0.25 6/0.25 7/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 6/0.25 7/1 0/2 |
L6/1.5 3/2.5 |
L5/1.5 3/2.5 |
L7/1.5 3/2.5 |
L7/1.5 2/2.5 |
1'/1.5 6/2.5 |
1'/1.5 5/2.5 |
L7/1.5 5/2.5 |
L7/1.5 5/2.5 |
3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 4/0.25 6/0.25 |
3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 2/0.25 5/0.25 |
L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 1/0.25 3/0.25 |
2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 1/0.25 5/0.25 |
3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 4/0.25 6/0.25 |
3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 2/0.25 5/0.25 |
L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 7/0.25 L7/0.25 3/0.25 1/0.25 3/0.25 |
2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 2/0.25 0/0.25 |
0/0.5 1/0.25 7/0.25 1/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 1/0.25 7/0.5 1/0.25 2/0.25 1/2 |
0/0.5 7/0.25 6/0.25 7/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 6/0.25 7/1 0/2 |
0/0.5 1/0.25 7/0.25 1/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 1/0.25 7/0.5 1/0.25 2/0.25 1/2 |
0/0.5 7/0.25 6/0.25 7/0.5 3/0.25 4/0.25 3/2 |
0/0.5 7/0.25 6/0.25 7/1 0/2 |
L6/1.5 3/2.5 |
L5/1.5 3/2.5 |
L7/1.5 3/2.5 |
L7/1.5 2/2.5 |
1'/1.5 6/2.5 |
1'/1.5 5/2.5 |
L7/1.5 5/2.5 |
L7/1.5 5/2.5 |
3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 4/0.25 6/0.25 |
3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 2/0.25 5/0.25 |
7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 1/0.25 3/0.25 |
2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 1/0.25 5/0.25 |
3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 R3/0.25 3/0.25 6/0.25 4/0.25 6/0.25 |
3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 R3/0.25 3/0.25 5/0.25 2/0.25 5/0.25 |
7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 7/0.25 7/0.25 3/0.25 1/0.25 3/0.25 |
2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 R2/0.25 2/0.25 5/0.25 1/0.25 5/0.25 |
R6/4`, jianpu: `0_ 1__ ,7__ 1_ 3__ 4__ 3- |
0_ ,7__ 1__ ,7_ 1__ 2__ 1- |
0_ ,7__ ,6__ ,7_ 3__ 4__ 3- |
0_ ,7__ ,6__ ,7 0- |
0_ 1__ ,7__ 1_ 3__ 4__ 3- |
0_ ,7__ 1__ ,7_ 1__ 2__ 1- |
0_ ,7__ ,6__ ,7_ 3__ 4__ 3- |
0_ ,7__ ,6__ ,7 0- |
,6. 3.- |
,5. 3.- |
,7. 3.- |
,7. 2.- |
1'. 6.- |
1'. 5.- |
,7. 5.- |
,7. 5.- |
3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 4__ 6__ |
3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 2__ 5__ |
,7__ 3__ 7__ ,7__ 3__ 7__ ,7__ 3__ 7__ ,7__ 3__ 7__ ,7__ 3__ 1__ 3__ |
2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 1__ 5__ |
3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 4__ 6__ |
3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 2__ 5__ |
,7__ 3__ 7__ ,7__ 3__ 7__ ,7__ 3__ 7__ ,7__ 3__ 7__ ,7__ 3__ 1__ 3__ |
2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2__ 0__ |
0_ 1__ ,7__ 1_ 3__ 4__ 3- |
0_ ,7__ 1__ ,7_ 1__ 2__ 1- |
0_ ,7__ ,6__ ,7_ 3__ 4__ 3- |
0_ ,7__ ,6__ ,7 0- |
0_ 1__ ,7__ 1_ 3__ 4__ 3- |
0_ ,7__ 1__ ,7_ 1__ 2__ 1- |
0_ ,7__ ,6__ ,7_ 3__ 4__ 3- |
0_ ,7__ ,6__ ,7 0- |
,6. 3.- |
,5. 3.- |
,7. 3.- |
,7. 2.- |
1'. 6.- |
1'. 5.- |
,7. 5.- |
,7. 5.- |
3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 4__ 6__ |
3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 2__ 5__ |
7__ 3__ 7__ 7__ 3__ 7__ 7__ 3__ 7__ 7__ 3__ 7__ 7__ 3__ 1__ 3__ |
2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 1__ 5__ |
3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 3'__ 3__ 6__ 4__ 6__ |
3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 3'__ 3__ 5__ 2__ 5__ |
7__ 3__ 7__ 7__ 3__ 7__ 7__ 3__ 7__ 7__ 3__ 7__ 7__ 3__ 1__ 3__ |
2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 2'__ 2__ 5__ 1__ 5__ |
6'---` },
  { title: "天空之城", detail: "4/4 · 87 BPM · 图片录入版", bpm: 87, score: `L6/0.5 L7/0.5 |
1/1.5 L7/0.5 1/1 3/1 |
L7/3 L3/1 |
L6/1.5 L5/0.5 L6/1 1/1 |
L5/3 L3/1 |
L4/1.5 L3/0.5 L4/0.5 1/1.5 |
L3/3 1/1 |
L7/1.5 LM4/0.5 LM4/1.5 L7/0.5 |
L7/3 L6/0.5 L7/0.5 |
1/1.5 L7/0.5 1/1 3/1 |
L7/3 L3/0.5 L3/0.5 |
L6/1.5 L5/0.5 L6/1 1/1 |
L5/3 L3/1 |
L4/1 1/0.5 L7/1.5 1/1 |
2/1 3/0.5 1/2.5 |
1/0.5 L7/0.5 L6/1 L7/1 LM5/1 |
L6/3 1/0.5 2/0.5 |
3/1.5 2/0.5 3/1 5/1 |
2/3 L5/1 |
1/1.5 L7/0.5 1/1 2/0.5 3/0.5 |
3/4 |
L6/0.5 L7/0.5 1/1 L7/0.5 1/0.5 2/1 |
1/1.5 L5/0.5 5/2 |
4/1 3/1 2/1 1/1 |
3/3 3/1 |
6/1.5 6/0.5 5/1.5 5/0.5 |
3/0.5 2/0.5 1/1 1/2 |
2/1.5 1/0.5 2/1 5/1 |
3/3 3/1 |
6/1.5 6/0.5 5/1.5 5/0.5 |
3/0.5 2/0.5 1/1 1/2 |
2/1.5 1/0.5 2/1 L7/1 |
L6/3 0/1` },
  { title: "皇后大道东", detail: "1=G · 4/4 · 118 BPM · 图片低音校对版", bpm: 118, score: `L6/0.5 0/0.5 L5/0.5 L6/0.5 0/2 |
L6/0.5 0/0.5 L5/0.5 L6/0.5 0/2 |
L5/0.5 L6/0.5 1/0.5 2/0.5 3/0.5 3/0.5 L6/1 |
2/0.5 3/0.5 1/0.5 L5/0.5 L6/1 0/1 |
3/1.5 3/0.5 3/0.5 3/0.5 6/0.5 3/0.5 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 0/1 |
2/0.5 2/0.5 2/0.5 2/0.5 5/0.5 1/0.5 2/1 |
1/0.5 1/0.5 1/0.5 1/0.5 3/1 0/1 |
3/1.5 3/0.5 3/0.5 3/0.5 6/0.5 3/0.5 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 0/1 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 2/1 |
1/0.5 1/0.5 1/0.5 2/0.5 3/1 0/1 |
1/0.5 1/0.5 1/0.5 L7/0.5 L6/0.5 L6/0.5 1/1 |
L7/0.5 L7/0.5 L7/0.5 1/0.5 L7/1 0/1 |
L7/0.5 L7/0.5 L7/0.5 L6/0.5 L5/1 L7/1 |
1/0.5 L6/0.5 L6/0.5 L5/0.5 L6/1 0/1 |
1/0.5 1/0.5 1/0.5 L7/0.5 L6/0.5 L6/0.5 1/1 |
2/0.5 2/0.5 2/0.5 3/0.5 2/1 0/1 |
L7/0.5 L7/0.5 L7/0.5 1/0.5 2/1 L5/1 |
1/0.5 L6/0.5 L6/0.5 L5/0.5 L6/1 0/1 |
3/1.5 3/0.5 3/0.5 3/0.5 3/0.5 1/0.5 |
2/0.5 2/0.5 2/0.5 2/0.5 3/1 0/1 |
4/0.5 4/0.5 4/0.5 4/0.5 4/1 4/1 |
3/0.5 3/0.5 3/0.5 2/0.5 3/1 0/1 |
1/0.5 1/0.5 1/0.5 L7/0.5 L6/1 3/1 |
2/0.5 2/0.5 2/0.5 3/0.5 2/1 0/1 |
L7/0.5 L7/0.5 L7/0.5 1/0.5 2/1 L5/1 |
1/0.5 L6/0.5 L6/0.5 L5/0.5 L6/1 0/1 |
1/0.5 L6/0.5 L6/0.5 L5/0.5 L6/1 0/1 |
0/4 |
0/4 |
1/0.5 L6/0.5 L6/0.5 L5/0.5 L6/1 0/1 |
3/1.5 3/0.5 3/0.5 3/0.5 6/0.5 3/0.5 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 0/1 |
2/0.5 2/0.5 2/0.5 2/0.5 5/0.5 1/0.5 2/1 |
1/0.5 1/0.5 1/0.5 1/0.5 3/1 0/1 |
3/1.5 3/0.5 3/0.5 3/0.5 6/0.5 3/0.5 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 0/1 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 2/1 |
1/0.5 1/0.5 1/0.5 2/0.5 3/1 0/1 |
3/1.5 3/0.5 3/0.5 3/0.5 6/0.5 3/0.5 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 0/1 |
2/0.5 2/0.5 2/0.5 2/0.5 5/0.5 1/0.5 2/1 |
1/0.5 1/0.5 1/0.5 1/0.5 3/1 0/1 |
3/1.5 3/0.5 3/0.5 3/0.5 6/0.5 3/0.5 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 0/1 |
2/0.5 2/0.5 2/0.5 2/0.5 5/1 2/1 |
1/0.5 1/0.5 1/0.5 2/0.5 3/1 0/1` },
  { title: "父亲", detail: "1=E · 4/4 · 68 BPM · 图片主旋律录入版", bpm: 68, jianpu: `1' 3' 2' 6_ 5_ |
6 5 3- |
1' 3' 2'. 5'_ |
3'-- 6_ 7_ |
1' 3' 2'_ 1'_ 7 |
1' 5_ 4_ 5 6_ 7_ |
1'. 3'_ 2'. 5'_ |
6--- |
1_ ,5_ 1_ 3__ 4__ 4_ 3_ 2_ 1_ |
1_ ,5_ 1_ 2_ 3 0 |
1_ ,5_ 1_ 3__ 4__ 4_ 3_ 2_ 1_ |
3_ 2_ 2__ 1__ 1. 0 |
1_ ,5_ 1_ 3_ 4_ 3_ 2_ 1_ |
6_ 5_ 5__ 4__ 4_ 3 0 |
1_ ,5_ 1_ 3_ 4_ 3_ 2_ 0__ 1__ |
3_ 2_ 2_ 1_ 1 0_ 1_ |
,6__ 6_. 6_ 5_ 3_ 3_ 0_ 3_ |
4_ 5_ 1_ 5__ 5__ 3 1_ ,7_ |
6_. 6_. 6_ 7__ 5__ 5_ 0_ 5_ |
6_ 5__ 4__ 4_ 3_ 3. 2_ |
2-- 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 7 0__ 6__ 7_ |
7__ 7__ 7 3'_ 2'__ 1'__ 1'_ 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 1'__ 7__ 6 7_ |
6_ 5__ 5:2.25 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 7 0__ 6__ 7_ |
7__ 7__ 7 3'_ 7_. 1'__ 0__ 6__ 7_ |
1'__ 1'__ 1' 3'_ 2' 7__ 6_. |
6-- 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 7 0__ 6__ 7_ |
7__ 7__ 7 3'_ 2'__ 1'__ 1'_ 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 1'__ 7__ 6 7_ |
6_ 5__ 5:2.25 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 7 0__ 6__ 7_ |
7__ 7__ 7 3'_ 7_. 1'__ 0__ 6__ 7_ |
1'__ 1'__ 1' 3'_ 2' 7__ 6_. |
6--- |
6-- 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 7 0__ 6__ 7_ |
7__ 7__ 7 3'_ 2'__ 1'__ 1'_ 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 1'__ 7__ 6 7_ |
6_ 5__ 5:2.25 0__ 6__ 7_ |
1'__ 1'__ 1' 1'_ 7 0__ 6__ 7_ |
7__ 7__ 7 3'_ 7_. 1'__ 0__ 6__ 7_ |
1'__ 1'__ 1' 3'_ 2' 7__ 6_. |
6--- |
,6--- |
,6_ ,3_ ,6_ ,7_ 1_ 3_ ,7 |
1_ ,5_ 1_ 3_ 4_ 3_ 2_ 1_ |
1_ ,5_ 1_ 2_ 3- |
1_ ,5_ 1_ 3_ 4_ 3_ 2_ 1_ |
3_ 2_ 2_ 1_ 1- |
1_ ,5_ 1_ 3_ 4_ 3_ 2_ 1_ |
6_ 5_ 5_ 4_. 4_ 3_. 0_ |
1_ ,5_ 1_ 3_ 4_ 3_ 2_ 1_ |
3_ 2_ 2_ 1_ 1- |
6-- 0__ 6__ 7_ |
1'__ 1'__ 1' 3'__ 2':2.25` },
  { title: "贝加尔湖畔", detail: "1=C · 4/4 · 临时 76 BPM（可修改）· 用户提供主旋律校订版", bpm: 76, jianpu: `0 ,6_ ,7_ 1 5 |
4- 0 0 |
0 ,5_ ,6_ ,7 4 |
3- 0 0 |
0 3_ 3_ 6 5 |
4 2- 0_ ,7_ |
,7 1_ 2. 4 |
3-- 0 |
0 ,6_ ,7_ 1 5 |
4- 0 0 |
0 ,5_ ,6_ ,7 4 |
3- 0 0 |
0 3_ 3_ 6 5 |
4 2- 0_ ,7_ |
,7 3_ 2. 1_ ,7_ |
,6 ,6_ ,6_ ,6 6 |
6-- 0 |
0 ,6_ 6_ 5 5__ 6__ 5_ |
3-- 0 |
0 3_ 3_ 6 5 |
4 2- 0_ 1_ |
,7 1_ 2_- 4 |
3-- 0 |
0 3_ 3_ 6 5 |
4 2- 0 |
5 6_ 7. 7 |
3'--- |
7--- |
0 0 0 0 |
0 ,6_ ,7_ 1 5 |
4- 0 0 |
0 ,5_ ,6_ ,7 4 |
3- 0 0 |
0 3_ 3_ 6 5_ 4_ |
4_ 2.- 0_ ,7_ |
,7 3_ 2. ,7_ 1_ |
,6-- 0 |` }
];

const BUILTIN_SONG_METADATA = {
  "鸟之诗": { artist: "Lia", key: "1=D", meter: "4/4" },
  "天使爱美丽": { artist: "Yann Tiersen", key: "1=G", meter: "4/4" },
  "天空之城": { artist: "久石让", key: "1=C", meter: "4/4" },
  "皇后大道东": { artist: "罗大佑", key: "1=G", meter: "4/4" },
  "父亲": { artist: "筷子兄弟", key: "1=E", meter: "4/4" },
  "贝加尔湖畔": { artist: "李健", key: "1=C", meter: "4/4" }
};
const PDMX_SONG_LIBRARY = Array.isArray(globalThis.PDMX_SONGS) ? globalThis.PDMX_SONGS : [];
const COMMUNITY_SONG_LIBRARY = Array.isArray(globalThis.COMMUNITY_SONGS) ? globalThis.COMMUNITY_SONGS : [];
const SONG_FILE_FORMAT = "delta-music";
const LEGACY_SONG_FILE_FORMAT = "harmonica-deck-score";
const SONG_FILE_VERSION = 1;
const SONG_LIBRARY = [...BUILTIN_SONG_LIBRARY, ...COMMUNITY_SONG_LIBRARY, ...PDMX_SONG_LIBRARY].map((song) => normalizeSong(song));
const MACRO_TRIGGER_MODE_LABELS = { once: "单次播放", hold: "长按播放", toggle: "切换播放" };
const MACRO_TRIGGER_MODE_HINTS = {
  once: "单次播放：按下后完整播放一次。播放中再次按下会忽略；没有停止键时无法中途停止。",
  hold: "长按播放：按住绑定键播放，松开后立即停止；也可用全局停止键中止。",
  toggle: "切换播放：按一下开始，再按同一个绑定键停止；也可另设全局停止键。"
};
const SECTION_GUIDES = {
  directory: {
    windowTitle: "HELP.EXE — QUICK START",
    index: "00 · QUICK START",
    title: "目录 · 从这里开始",
    intro: "目录只负责把你带到正确的起点；曲谱和导出内容始终在当前浏览器中处理。",
    steps: [
      ["01", "使用曲库", "点击卡片主体可载入编辑器；右上角「导出」会载入该曲并直接前往最后的导出区。卡片内的「教程」会带你逐步完成此路径。"],
      ["02", "导入 MIDI", "选择 MIDI 文件后，先选择旋律音轨与截取范围，再确认生成；可按需要关闭「流畅演奏」，保留短断音。"],
      ["03", "手动打谱", "从简谱模式开始输入数字简谱；也可在编辑器内切换到录制、精确或三角洲键盘模式。每张入口卡内都有对应教程。"]
    ]
  },
  library: {
    windowTitle: "HELP.EXE — SONG LIBRARY",
    index: "02 · SCORE ARCHIVE",
    title: "曲库 · 选曲与载入",
    intro: "曲库用于快速载入现成曲谱。载入会同时刷新歌名、作者、调号、拍号、BPM 和各个输入格式。",
    steps: [
      ["01", "查找曲目", "在搜索框输入曲名、拍号、调号、速度或共享人，可即时筛选曲库。"],
      ["02", "点击卡片或「编辑」", "两种操作都会载入该曲并定位到编辑器。随后可修改谱子、歌曲信息与速度。"],
      ["03", "使用「导出」", "会先载入当前曲目，再跳转到最后的导出为宏区域，不需要重复选曲。"],
      ["04", "提交作品", "点击「我要上传」查看群聊提交方式；共享前建议导出 <code>.deltamusic</code> 以保留曲谱和元信息。"]
    ]
  },
  editor: {
    windowTitle: "HELP.EXE — SCORE EDITOR",
    index: "03 · INPUT WORKBENCH",
    title: "编辑器 · 输入与校验",
    intro: "编辑器会把不同写法统一为同一套按键事件。每次输入后会校验，并同步播放器与导出数据。",
    steps: [
      ["01", "导入来源与流畅演奏", "「导入 MIDI」会先显示每条音轨和截取范围；确认后才写入曲谱。「导入 .deltamusic」恢复已保存的曲谱；流畅演奏会连接 MIDI 的短断音。"],
      ["02", "简谱模式", "适合日常打谱：数字为音级，<code>0</code> 为休止，<code>-</code> 延长一拍，<code>_</code> 为半拍，<code>.</code> 为附点；可写升降号与高低音。"],
      ["03", "录制模式", "点击开始录制后，使用 Z–M、逗号或页面琴键实时弹奏；松开按键结束当前音，录制结果会量化到当前 BPM。"],
      ["04", "精确模式", "使用 <code>音符/拍数</code> 逐音控制时值，例如 <code>L4/0.5</code>。L、M、R 分别代表左键降调、中键半音、右键升调，可组合使用。"],
      ["05", "三角洲键盘模式", "每行输入一个「按键 / 毫秒」事件，例如 <code>左键 + Z / 250ms</code> 或 <code>等待 / 500ms</code>，方便对照第三方宏工具。"],
      ["06", "曲目信息与编辑区", "歌名、作者、调号、拍号和 BPM 会随导出保存。编辑区左侧行号与下方语法提示用于定位和修正输入。"],
      ["07", "校验、试听与分享", "底部校验会给出错误行列或预计时长；「试听」播放当前序列，「分享 .deltamusic」保存曲谱，「导出为宏」前往导出区。"],
      ["08", "播放器", "总时长、音符与事件统计用于核对；试听、从头播放、停止、音量与进度控制只影响浏览器试听。事件时间线可点击跳转到指定时刻。"],
      ["09", "导出目标", "导出区提供 Logitech G HUB Lua、Razer Synapse 3 XML、Synapse 4 XML 和手动键盘谱；请按设备与软件版本选择，并确认使用环境允许宏。"]
    ]
  },
  player: {
    windowTitle: "HELP.EXE — PLAYBACK",
    index: "04 · PLAYBACK STATUS",
    title: "播放器 · 听谱与检查",
    intro: "播放器用于在导出前确认旋律和节奏。它不控制游戏或鼠标软件，只在浏览器内试听当前曲谱。",
    steps: [
      ["01", "试听整段", "点击「试听整段」从当前序列开始播放；「从头播放」可重新开始，「停止」会立即结束试听。"],
      ["02", "调节音量", "使用 VOL 滑杆调整浏览器试听音量，不会影响导出的 Lua、XML 或键盘谱时值。"],
      ["03", "核对统计", "总时长、音符数和输入事件数会随谱子更新；它们可帮助发现意外的休止或重复。"],
      ["04", "查看事件时间线", "时间线逐项显示按键、变调键、按住时长与气口。点击任一行可跳到该时刻并开始试听。"]
    ]
  },
  export: {
    windowTitle: "HELP.EXE — MACRO EXPORT",
    index: "05 · DRIVER FILES",
    title: "导出为宏 · 配置与交付",
    intro: "在这里将已校验的曲谱输出为鼠标软件脚本、XML 文件，或查看便于手动录入的键盘事件。请先确认目标环境允许使用宏。",
    steps: [
      ["01", "设置 G HUB 触发", "填写绑定鼠标键并选择单次、长按或切换播放。全局停止键可选，用于随时终止正在播放的 Lua。"],
      ["02", "导出 Logitech Lua", "可先「复制 Lua」审阅内容，或下载 <code>.lua</code>。在 Logitech G HUB 的目标配置文件中打开脚本 / Scripting 页面，粘贴并保存。"],
      ["03", "导出 Razer XML", "Synapse 3 与 4 分别生成 XML；导入后仍需在相应版本内手动绑定鼠标键与触发模式。"],
      ["04", "手动输入宏", "点击「查看键盘谱」打开当前曲目的三角洲键盘模式；每一行都是按键或等待事件，可按此在其他工具逐项录入。"]
    ]
  }
};

const elements = {
  score: document.querySelector("#score"), jianpuScore: document.querySelector("#jianpuScore"), recordedScore: document.querySelector("#recordedScore"), keyboardScore: document.querySelector("#keyboardScore"), bpm: document.querySelector("#bpm"), macroName: document.querySelector("#macroName"), artistName: document.querySelector("#artistName"), keySignature: document.querySelector("#keySignature"), timeSignature: document.querySelector("#timeSignature"), macroTriggerButton: document.querySelector("#macroTriggerButton"), macroStopButton: document.querySelector("#macroStopButton"), macroTriggerMode: document.querySelector("#macroTriggerMode"), macroSettings: document.querySelector("#macroSettings"), macroSettingsHint: document.querySelector("#macroSettingsHint"), macroTriggerValidation: document.querySelector("#macroTriggerValidation"),
  workbench: document.querySelector(".workbench"), editorPanel: document.querySelector(".editor-panel"),
  convertButton: document.querySelector("#convertButton"), clearButton: document.querySelector("#clearButton"), importMidiButton: document.querySelector("#importMidiButton"), importMidiInput: document.querySelector("#importMidiInput"), midiSmoothing: document.querySelector("#midiSmoothing"), midiTrackPicker: document.querySelector("#midiTrackPicker"), midiTrackList: document.querySelector("#midiTrackList"), midiPickerStatus: document.querySelector("#midiPickerStatus"), midiRangeStart: document.querySelector("#midiRangeStart"), midiRangeEnd: document.querySelector("#midiRangeEnd"), midiRangeSummary: document.querySelector("#midiRangeSummary"), midiRangeSliders: document.querySelector("#midiRangeSliders"), midiRangeStartInput: document.querySelector("#midiRangeStartInput"), midiRangeEndInput: document.querySelector("#midiRangeEndInput"), confirmMidiSelection: document.querySelector("#confirmMidiSelection"), importScoreButton: document.querySelector("#importScoreButton"), macroExportButton: document.querySelector("#macroExportButton"), macroExportSection: document.querySelector("#macro-export"), exportScoreButton: document.querySelector("#exportScoreButton"), importScoreInput: document.querySelector("#importScoreInput"),
  lineNumbers: document.querySelector("#lineNumbers"), jianpuLineNumbers: document.querySelector("#jianpuLineNumbers"), keyboardLineNumbers: document.querySelector("#keyboardLineNumbers"), validation: document.querySelector("#validation"), status: document.querySelector("#parseStatus"),
  totalTime: document.querySelector("#totalTime"), noteCount: document.querySelector("#noteCount"), eventCount: document.querySelector("#eventCount"), beatMs: document.querySelector("#beatMs"),
  timeline: document.querySelector("#timeline"), monitorDot: document.querySelector(".monitor-dot"), toast: document.querySelector("#toast"), exportButtons: [...document.querySelectorAll("[data-action]")],
  previewButton: document.querySelector("#previewButton"), restartButton: document.querySelector("#restartButton"), stopButton: document.querySelector("#stopButton"), volume: document.querySelector("#volume"), previewState: document.querySelector("#previewState"), previewProgress: document.querySelector("#previewProgress"), previewProgressLabel: document.querySelector("#previewProgressLabel"),
  inputModeButtons: [...document.querySelectorAll("[data-input-mode]")], inputPanes: [...document.querySelectorAll("[data-input-pane]")], directoryButtons: [...document.querySelectorAll("[data-directory-action]")], tourStartButtons: [...document.querySelectorAll("[data-tour-start]")], guideButtons: [...document.querySelectorAll("[data-guide]")], sectionGuideDialog: document.querySelector("#sectionGuideDialog"), sectionGuideWindowTitle: document.querySelector("#sectionGuideWindowTitle"), sectionGuideIndex: document.querySelector("#sectionGuideIndex"), sectionGuideHeading: document.querySelector("#sectionGuideHeading"), sectionGuideIntro: document.querySelector("#sectionGuideIntro"), sectionGuideSteps: document.querySelector("#sectionGuideSteps"), songGrid: document.querySelector("#songGrid"), songSearch: document.querySelector("#songSearch"), libraryCount: document.querySelector("#libraryCount"), uploadScoreButton: document.querySelector("#uploadScoreButton"), localLibraryButton: document.querySelector("#localLibraryButton"), uploadHelpDialog: document.querySelector("#uploadHelpDialog"), uploadCopyStatus: document.querySelector("#uploadCopyStatus"),
  recordToggle: document.querySelector("#recordToggle"), recordState: document.querySelector("#recordState"), recordCount: document.querySelector("#recordCount"), recordKeyboard: document.querySelector("#recordKeyboard"), modifierChoices: [...document.querySelectorAll("[data-record-modifier]")],
  qqGroupButton: document.querySelector("#qqGroupButton"), macroDownloadDialog: document.querySelector("#macroDownloadDialog"), macroDownloadFilename: document.querySelector("#macroDownloadFilename"), macroDownloadProgress: document.querySelector("#macroDownloadProgress"), macroDownloadProgressLabel: document.querySelector("#macroDownloadProgressLabel"), confirmMacroDownload: document.querySelector("#confirmMacroDownload"), scoreExportDialog: document.querySelector("#scoreExportDialog"), scoreExportTitle: document.querySelector("#scoreExportTitle"), scoreExportHeading: document.querySelector("#scoreExportHeading"), scoreExportDescription: document.querySelector("#scoreExportDescription"), exportSongTitle: document.querySelector("#exportSongTitle"), exportArtistName: document.querySelector("#exportArtistName"), exportSharedBy: document.querySelector("#exportSharedBy"), exportMetaPreview: document.querySelector("#exportMetaPreview"), confirmScoreExport: document.querySelector("#confirmScoreExport"), confirmScoreExportLabel: document.querySelector("#confirmScoreExportLabel"), confirmScoreExportIcon: document.querySelector("#confirmScoreExportIcon"), manualMacroButton: document.querySelector("#manualMacroButton"), keyboardMacroDialog: document.querySelector("#keyboardMacroDialog"), keyboardMacroTitle: document.querySelector("#keyboardMacroTitle"), keyboardMacroMeta: document.querySelector("#keyboardMacroMeta"), keyboardMacroOutput: document.querySelector("#keyboardMacroOutput"),
  tourLayer: document.querySelector("#tourLayer"), tourSpotlight: document.querySelector("#tourSpotlight"), tourPopover: document.querySelector("#tourPopover"), tourIndex: document.querySelector("#tourIndex"), tourTitle: document.querySelector("#tourTitle"), tourCopy: document.querySelector("#tourCopy"), tourStatus: document.querySelector("#tourStatus"), tourProgress: document.querySelector("#tourProgress"), tourPrevious: document.querySelector("#tourPrevious"), tourNext: document.querySelector("#tourNext"), tourSkip: document.querySelector("#tourSkip"), tourClose: document.querySelector("#tourClose")
};

let currentSequence = null;
let audioContext = null;
let masterGain = null;
const harmonicaWaveCache = new WeakMap();
const harmonicaNoiseCache = new WeakMap();
let activePreview = null;
let workbenchHeightSyncFrame = 0;
let pendingMacroDownload = null;
let macroDownloadTimer = null;
let macroDownloadFinalizeTimer = null;
let inputMode = "jianpu";
let lastMidiFile = null;
let midiImportState = null;
let previewCursorMs = 0;
let previewProgressFrame = 0;
let activeTour = null;
const PREVIEW_SCHEDULE_AHEAD_MS = 2500;
const PREVIEW_SCHEDULER_INTERVAL_MS = 100;

const TOUR_FLOWS = {
  library: [
    { index: "曲库教程 · 01", target: ".library-deck", title: "从曲库开始", copy: "这里收录内置与社区曲目。搜索后，在任意曲目卡片右上角使用「导出」可直接带着该曲进入最后的导出区。" },
    { index: "曲库教程 · 02", target: () => document.querySelector("[data-song-action='export']"), interactiveSelector: "[data-song-action='export']", title: "选择一首曲目并导出", copy: "请选择想要的曲目，然后点击它右上角的「导出」。工具会自动载入曲谱、同步编辑器与播放器，并跳到导出为宏。", action: "library-export", status: "等待你点击任意曲目右上角的「导出」。" },
    { index: "曲库教程 · 03", target: "#macro-export", title: "按设备选择导出方式", copy: "Logitech G HUB 使用 Lua；Razer Synapse 3 与 4 必须分别使用对应 XML；没有直接导入方式的工具可查看「手动输入宏」并逐项录入按键/毫秒。请先确认目标环境允许宏。", terminal: true }
  ],
  midi: [
    { index: "MIDI 教程 · 01", target: "#importMidiButton", title: "导入你的 MIDI", copy: "点击「导入 MIDI」并选择本地 .mid 或 .midi 文件。为保护本地文件权限，只有你能在系统文件选择器中选择文件。", action: "midi-file", status: "等待你选择 MIDI 文件。取消后可再次点击导入。" },
    { index: "MIDI 教程 · 02", target: "#midiTrackPicker", title: "选择旋律音轨并截取", copy: "先选含主旋律的音轨，再拖动开始与结束手柄保留所需片段。音轨与截取可以反复调整；完成后点击「确定并生成谱子」。", action: "midi-confirm", status: "等待你选择音轨、截取片段，并点击「确定并生成谱子」。" },
    { index: "MIDI 教程 · 03", target: ".editor-actions", title: "查看谱子、试播和导出", copy: "生成的简谱会同步显示在编辑器中。可先点击「试听」检查效果；准备好后点击「导出为宏」进入最后一步。", action: "macro-export", status: "等待你点击「导出为宏」。" },
    { index: "MIDI 教程 · 04", target: "#macro-export", title: "按设备选择导出方式", copy: "G HUB 使用 Lua；Synapse 3 与 4 分别导入各自版本的 XML；其他工具可按「手动输入宏」中的键盘谱逐项录入。", terminal: true }
  ],
  manual: [
    { index: "打谱教程 · 01", target: ".editor-panel", title: "打谱从编辑器开始", copy: "编辑器中的四种写法共享一首曲谱；切换模式时旋律和时值会自动同步。" },
    { index: "打谱教程 · 02", target: "[data-input-mode='jianpu']", title: "简谱模式", copy: "适合日常打谱。数字代表音级；0 为休止，- 延长一拍，_ 为半拍，. 为附点，可加入升降号和高低音。" },
    { index: "打谱教程 · 03", target: "[data-input-mode='record']", title: "录制模式", copy: "适合边弹边记。开始录制后使用 Z–M、逗号或页面琴键演奏，松开按键结束当前音；结果按 BPM 量化。" },
    { index: "打谱教程 · 04", target: "[data-input-mode='precise']", title: "精确模式", copy: "适合校谱和微调时值。以「音符/拍数」输入，例如 L4/0.5；L、M、R 分别代表左、中、右鼠标变调键。" },
    { index: "打谱教程 · 05", target: "[data-input-mode='keyboard']", title: "三角洲键盘模式", copy: "适合对照第三方宏工具。每行写一个「按键 / 毫秒」事件，例如「左键 + Z / 250ms」或「等待 / 500ms」。" },
    { index: "打谱教程 · 06", target: ".editor-panel .panel-guide-button", title: "完整打谱文档", copy: "右上角问号会打开完整参考，包含四种模式的语法、导入与截取、编辑器、播放器和导出功能。" },
    { index: "打谱教程 · 07", target: ".source-import-panel", title: "导入与演奏设置", copy: "可导入 MIDI 或 .deltamusic；MIDI 会先让你选音轨和片段。「流畅演奏」会自动连接短断音。" },
    { index: "打谱教程 · 08", target: ".controls-grid", title: "曲目信息", copy: "歌名、作者、调号、拍号和 BPM 会跟随当前曲谱。BPM 同时影响简谱、精确谱和录制结果的时值。" },
    { index: "打谱教程 · 09", target: ".input-pane:not([hidden])", title: "当前编辑区", copy: "在这里输入或微调曲谱；左侧行号和下方语法说明帮助定位格式问题。切换模式不会改变同一旋律的实际时值。" },
    { index: "打谱教程 · 10", target: ".editor-actions", title: "校验、试听与导出", copy: "「试听」播放当前序列；下方校验提示错误位置或预计时长。「分享」保存 .deltamusic；导出为宏会带你到最终导出区。" },
    { index: "打谱教程 · 11", target: ".meter-grid", title: "播放器统计", copy: "总时长、音符数和输入事件数随曲谱更新，可帮助发现意外休止、重复或时值问题。" },
    { index: "打谱教程 · 12", target: ".preview-console", title: "播放器控制", copy: "这里可以试听、从头播放、停止、调节音量和拖动播放进度。这些控制只影响浏览器试听，不会修改导出的宏。" },
    { index: "打谱教程 · 13", target: "#timeline", title: "事件时间线", copy: "每一行显示一个按键时刻、变调键、按住时长与气口。点击任意一行可从该位置开始试听。" },
    { index: "打谱教程 · 14", target: "#macroExportButton", title: "进入导出", copy: "完成打谱和试听后，点击「导出为宏」进入最后一步。", action: "macro-export", status: "等待你点击「导出为宏」。" },
    { index: "打谱教程 · 15", target: "#macro-export", title: "按设备选择导出方式", copy: "G HUB 使用 Lua；Synapse 3 与 4 分别使用自己的 XML；其他宏工具可使用手动输入的键盘谱。", terminal: true }
  ]
};

function resolveTourTarget(step) {
  return typeof step.target === "function" ? step.target() : document.querySelector(step.target);
}

function updateTourPosition() {
  if (!activeTour) return;
  const step = activeTour.steps[activeTour.stepIndex];
  const target = resolveTourTarget(step);
  if (!target) return;
  const rect = target.getBoundingClientRect();
  const padding = 7;
  const margin = 12;
  const gap = 16;
  Object.assign(elements.tourSpotlight.style, {
    left: `${Math.max(4, rect.left - padding)}px`, top: `${Math.max(4, rect.top - padding)}px`,
    width: `${Math.min(window.innerWidth - 8, rect.width + padding * 2)}px`, height: `${Math.min(window.innerHeight - 8, rect.height + padding * 2)}px`
  });
  const safeLeft = Math.max(0, rect.left - padding);
  const safeTop = Math.max(0, rect.top - padding);
  const safeRight = Math.min(window.innerWidth, rect.right + padding);
  const safeBottom = Math.min(window.innerHeight, rect.bottom + padding);
  const safeHeight = Math.max(0, safeBottom - safeTop);
  const shieldBounds = {
    ".tour-shield-top": [0, 0, window.innerWidth, safeTop],
    ".tour-shield-right": [safeRight, safeTop, Math.max(0, window.innerWidth - safeRight), safeHeight],
    ".tour-shield-bottom": [0, safeBottom, window.innerWidth, Math.max(0, window.innerHeight - safeBottom)],
    ".tour-shield-left": [0, safeTop, safeLeft, safeHeight]
  };
  Object.entries(shieldBounds).forEach(([selector, [left, top, width, height]]) => {
    Object.assign(document.querySelector(selector).style, { left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px` });
  });

  // Informational steps do not require an underlying click. Center their card
  // so a large panel target cannot collapse the tutorial controls.
  if (!step.action) {
    elements.tourPopover.style.removeProperty("--tour-popover-max-height");
    const infoPopover = elements.tourPopover.getBoundingClientRect();
    elements.tourPopover.style.top = `${Math.max(margin, (window.innerHeight - infoPopover.height) / 2)}px`;
    elements.tourPopover.style.left = `${Math.max(margin, (window.innerWidth - infoPopover.width) / 2)}px`;
    return;
  }

  // Reset the size constraint before measuring the next target. A tall tour
  // card previously overlapped the very control it asked the user to click.
  elements.tourPopover.style.removeProperty("--tour-popover-max-height");
  const popoverRect = elements.tourPopover.getBoundingClientRect();
  const below = window.innerHeight - rect.bottom - gap - margin;
  const above = rect.top - gap - margin;
  const right = window.innerWidth - rect.right - gap - margin;
  const left = rect.left - gap - margin;
  const needsSidePlacement = Math.max(above, below) < 260 && Math.max(left, right) >= popoverRect.width;

  let top;
  let horizontal;
  if (needsSidePlacement) {
    const placeRight = right >= left && right >= popoverRect.width;
    horizontal = placeRight ? rect.right + gap : rect.left - gap - popoverRect.width;
    const availableHeight = window.innerHeight - margin * 2;
    elements.tourPopover.style.setProperty("--tour-popover-max-height", `${availableHeight}px`);
    const constrainedHeight = elements.tourPopover.getBoundingClientRect().height;
    top = Math.max(margin, Math.min(window.innerHeight - constrainedHeight - margin, rect.top + (rect.height - constrainedHeight) / 2));
  } else {
    const placeBelow = below >= above;
    const availableHeight = Math.max(0, placeBelow ? below : above);
    elements.tourPopover.style.setProperty("--tour-popover-max-height", `${availableHeight}px`);
    const constrainedHeight = elements.tourPopover.getBoundingClientRect().height;
    top = placeBelow ? rect.bottom + gap : rect.top - gap - constrainedHeight;
    horizontal = Math.max(margin, Math.min(window.innerWidth - popoverRect.width - margin, rect.left));
  }
  elements.tourPopover.style.top = `${top}px`;
  elements.tourPopover.style.left = `${horizontal}px`;
}

function renderTourStep({ scroll = true } = {}) {
  if (!activeTour) return;
  document.querySelectorAll(".tour-target").forEach((element) => element.classList.remove("tour-target"));
  const step = activeTour.steps[activeTour.stepIndex];
  const target = resolveTourTarget(step);
  if (!target) { endTour(); return; }
  // Smooth scrolling can leave the popover positioned for an intermediate
  // target location, covering the control once the scroll finishes.
  if (scroll) target.scrollIntoView({ behavior: "auto", block: "center", inline: "nearest" });
  target.classList.add("tour-target");
  elements.tourIndex.textContent = step.index;
  elements.tourTitle.textContent = step.title;
  elements.tourCopy.textContent = step.copy;
  elements.tourStatus.textContent = step.status || "";
  elements.tourStatus.hidden = !step.status;
  elements.tourProgress.innerHTML = activeTour.steps.map((_, index) => `<i class="${index === activeTour.stepIndex ? "active" : ""}"></i>`).join("");
  elements.tourPrevious.hidden = activeTour.stepIndex === 0;
  elements.tourNext.disabled = Boolean(step.action);
  elements.tourNext.querySelector("span").textContent = step.terminal ? "完成" : "下一步";
  elements.tourNext.querySelector("b").textContent = step.terminal ? "✓" : "→";
  window.requestAnimationFrame(updateTourPosition);
  window.setTimeout(updateTourPosition, scroll ? 120 : 0);
  window.setTimeout(updateTourPosition, scroll ? 520 : 0);
}

function startTour(name, returnFocus = document.activeElement) {
  const steps = TOUR_FLOWS[name];
  if (!steps) return;
  stopPreview();
  if (name === "manual") setInputMode("jianpu", { force: true, silent: true });
  activeTour = { name, steps, stepIndex: 0, returnFocus };
  elements.tourLayer.hidden = false;
  elements.tourLayer.setAttribute("aria-hidden", "false");
  renderTourStep();
  window.setTimeout(() => elements.tourSkip.focus(), 350);
}

function endTour() {
  document.querySelectorAll(".tour-target").forEach((element) => element.classList.remove("tour-target"));
  const returnFocus = activeTour?.returnFocus;
  activeTour = null;
  elements.tourLayer.hidden = true;
  elements.tourLayer.setAttribute("aria-hidden", "true");
  returnFocus?.focus?.({ preventScroll: true });
}

function moveTour(delta) {
  if (!activeTour) return;
  const nextIndex = activeTour.stepIndex + delta;
  if (nextIndex >= activeTour.steps.length) { endTour(); return; }
  if (nextIndex < 0) return;
  activeTour.stepIndex = nextIndex;
  renderTourStep();
}

function completeTourAction(action, status = "操作完成，正在进入下一步。") {
  if (!activeTour || activeTour.steps[activeTour.stepIndex].action !== action) return;
  elements.tourStatus.textContent = status;
  elements.tourStatus.hidden = false;
  window.setTimeout(() => moveTour(1), 140);
}

function setTourStatus(status) {
  if (!activeTour) return;
  elements.tourStatus.textContent = status;
  elements.tourStatus.hidden = false;
}

function syncWorkbenchHeight() {
  if (!elements.workbench || !elements.editorPanel) return;
  if (window.matchMedia("(max-width: 860px)").matches) {
    elements.workbench.style.removeProperty("--workbench-height");
    return;
  }
  const editorHeight = Math.ceil(elements.editorPanel.getBoundingClientRect().height);
  if (editorHeight > 0) elements.workbench.style.setProperty("--workbench-height", `${editorHeight}px`);
}

function scheduleWorkbenchHeightSync() {
  window.cancelAnimationFrame(workbenchHeightSyncFrame);
  workbenchHeightSyncFrame = window.requestAnimationFrame(syncWorkbenchHeight);
}
let recording = null;
let selectedRecordModifier = "";
let liveRecordingVoice = null;
let currentScoreCredit = { artist: "", sharedBy: "" };
let scoreExportMode = "download";

function tokenPosition(source, offset) {
  const before = source.slice(0, offset);
  return { line: before.split("\n").length, column: offset - before.lastIndexOf("\n") };
}

function pitchCandidates() {
  const candidates = [{ midi: 72, note: "1'", modifier: null }];
  Object.entries(DIATONIC_MIDI).forEach(([note, midi]) => candidates.push({ midi, note, modifier: null }));
  Object.entries(DIATONIC_MIDI).forEach(([note, midi]) => candidates.push({ midi: midi + 1, note, modifier: "M" }));
  Object.entries(DIATONIC_MIDI).forEach(([note, midi]) => candidates.push({ midi: midi - 12, note, modifier: "L" }));
  Object.entries(DIATONIC_MIDI).forEach(([note, midi]) => candidates.push({ midi: midi + 12, note, modifier: "R" }));
  Object.entries(DIATONIC_MIDI).forEach(([note, midi]) => candidates.push({ midi: midi - 11, note, modifier: "LM" }));
  Object.entries(DIATONIC_MIDI).forEach(([note, midi]) => candidates.push({ midi: midi + 13, note, modifier: "RM" }));
  return candidates;
}

const PLAYABLE_PITCHES = pitchCandidates();

function encodeJianpuPitch(accidental, lowMark, digit, highMark) {
  if (digit === "0") {
    if (accidental || lowMark || highMark) return null;
    return { note: "0", modifier: null };
  }
  const octave = (highMark ? 12 : 0) - (lowMark ? 12 : 0);
  const accidentalOffset = accidental === "#" || accidental === "♯" ? 1 : accidental === "b" || accidental === "♭" ? -1 : 0;
  const midi = DIATONIC_MIDI[digit] + octave + accidentalOffset;
  return PLAYABLE_PITCHES.find((candidate) => candidate.midi === midi) || null;
}

function parseJianpu(source, bpm) {
  if (!source.trim()) return { error: { message: "请先输入至少一个简谱音符。", line: 1, column: 1 } };
  const notes = [];
  let tiePending = false;
  const tokens = [...source.matchAll(/\|\|:|:\|\||\|+|[^\s|]+/g)];
  for (const match of tokens) {
    let token = match[0].replace(/[—–]/g, "-").replace(/[·。]/g, ".").replace(/[，、]$/, "");
    const position = tokenPosition(source, match.index);
    if (/^(?:\|+|\|\|:|:\|\||:|\(|\)|\[|\]|\{|\})$/.test(token)) continue;
    if (/^[1-7]=[A-G](?:[#b♯♭])?$/i.test(token) || /^\d+\/\d+$/.test(token) || /^(?:♩|♪)=?\d+$/.test(token)) continue;
    token = token.replace(/^[([{]+/, "").replace(/[)\]}]+$/, "");
    if (!token) continue;
    if (/^-+$/.test(token)) {
      if (!notes.length) return { error: { message: "延音线前必须先有音符或休止符。", ...position } };
      notes[notes.length - 1].beats += token.length;
      continue;
    }
    if (token === "~") {
      if (!notes.length) return { error: { message: "连音线前必须先有音符。", ...position } };
      tiePending = true;
      continue;
    }
    const found = token.match(/^([#b♯♭]?)(,?)(0|[1-7])('?)(_{0,2})(\.*)(-*)(?::(\d+(?:\.\d+)?))?(~?)$/);
    if (!found) return { error: { message: `无法识别“${match[0]}”。可输入 5、0、#4、1'、,1、5_、5.，或用 5:1.25 写精确拍数。`, ...position } };
    const [, accidental, lowMark, digit, highMark, underscores, dots, dashes, explicitBeats, tieMark] = found;
    if (lowMark && highMark) return { error: { message: "同一个音不能同时标记高八度和低八度。", ...position } };
    const pitch = encodeJianpuPitch(accidental, lowMark, digit, highMark);
    if (!pitch) return { error: { message: `“${match[0]}”超出当前游戏键位可表达的音域。`, ...position } };
    if (explicitBeats && (underscores || dots || dashes)) return { error: { message: "精确拍数不能与下划线、附点或延音线同时使用。", ...position } };
    const baseBeats = 1 / (2 ** underscores.length);
    const dotFactor = dots.length ? 2 - (1 / (2 ** dots.length)) : 1;
    const beats = explicitBeats ? Number(explicitBeats) : baseBeats * dotFactor + dashes.length;
    if (!Number.isFinite(beats) || beats <= 0) return { error: { message: "拍数必须是大于 0 的数字。", ...position } };
    const item = { ...pitch, beats, start: match.index, ...position };
    const previous = notes[notes.length - 1];
    const samePitch = previous && (
      (Number.isFinite(previous.midi) && Number.isFinite(item.midi) && previous.midi === item.midi) ||
      (previous.note === item.note && previous.modifier === item.modifier)
    );
    if (tiePending && samePitch) previous.beats += item.beats;
    else notes.push(item);
    tiePending = Boolean(tieMark);
  }
  if (tiePending) return { error: { message: "连音线后缺少相同音高的音符。", line: source.split("\n").length, column: source.length - source.lastIndexOf("\n") } };
  if (!notes.length) return { error: { message: "没有找到可演奏的简谱音符。", line: 1, column: 1 } };
  return enrichNotes(notes, bpm);
}

function enrichNotes(notes, bpm) {
  if (!Number.isFinite(bpm) || bpm < 30 || bpm > 300) return { error: { message: "BPM 必须在 30 到 300 之间。", line: 1, column: 1 } };
  const beatMs = 60000 / bpm;
  let cursor = 0;
  const enriched = notes.map((item) => {
    const isRest = item.note === "0";
    const durationMs = Math.round(item.beats * beatMs);
    const eventCount = isRest ? 0 : 2 + (item.modifier?.length || 0) * 2;
    const event = { ...item, key: NOTE_KEYS[item.note] || null, isRest, durationMs, pressMs: isRest ? 0 : durationMs, waitMs: 0, timeMs: cursor, eventCount };
    cursor += durationMs;
    return event;
  });
  enriched.forEach((event, index) => {
    const next = enriched[index + 1];
    if (event.isRest || !next || next.isRest) return;
    const transitionMs = Math.min(INPUT_TRANSITION_GAP_MS, Math.max(0, event.durationMs - MIN_NOTE_HOLD_MS));
    event.pressMs = event.durationMs - transitionMs;
    event.waitMs = transitionMs;
  });
  return { notes: enriched, beatMs: Math.round(beatMs), totalMs: cursor, events: enriched.reduce((sum, item) => sum + item.eventCount, 0) };
}

function macroMidi(item) {
  const baseMidi = PREVIEW_MIDI[item.note];
  if (!Number.isFinite(baseMidi)) return null;
  return [...(item.modifier || "")].reduce((midi, modifier) => midi + (PREVIEW_OFFSETS[modifier] || 0), baseMidi);
}

function parseScore(source, bpm) {
  if (!source.trim()) return { error: { message: "请先输入至少一个音符。", line: 1, column: 1 } };
  if (!Number.isFinite(bpm) || bpm < 30 || bpm > 300) return { error: { message: "BPM 必须在 30 到 300 之间。", line: 1, column: 1 } };
  const notes = [];
  const tokens = [...source.matchAll(/\S+/g)];
  for (const match of tokens) {
    const token = match[0];
    if (token === "|") continue;
    const position = tokenPosition(source, match.index);
    const found = token.match(/^([LMRlmr]{0,2})(0|1'|[1-7])\/(\d+(?:\.\d+)?)$/);
    if (!found) {
      return { error: { message: `无法识别“${token}”。请使用例如 M2/0.5 的格式。`, ...position } };
    }
    const modifier = found[1].trim().toUpperCase() || null;
    const note = found[2];
    const beats = Number(found[3]);
    if (!Number.isFinite(beats) || beats <= 0) return { error: { message: "拍数必须是大于 0 的数字。", ...position } };
    if (note === "0" && modifier) return { error: { message: "休止符不能添加变调前缀。", ...position } };
    if (modifier && (new Set(modifier).size !== modifier.length || (modifier.includes("L") && modifier.includes("R")))) return { error: { message: "变调前缀不能重复，也不能同时使用 L 与 R。", ...position } };
    notes.push({ note, key: NOTE_KEYS[note] || null, modifier, isRest: note === "0", beats, start: match.index, ...position });
  }
  if (!notes.length) return { error: { message: "小节线不是音符，请输入例如 1/1。", line: 1, column: 1 } };
  return enrichNotes(notes, bpm);
}

function parseKeyboardScore(source, bpm) {
  if (!source.trim()) return { error: { message: "请先输入至少一项按键或等待时值。", line: 1, column: 1 } };
  if (!Number.isFinite(bpm) || bpm < 30 || bpm > 300) return { error: { message: "BPM 必须在 30 到 300 之间。", line: 1, column: 1 } };
  const notes = [];
  const beatMs = 60000 / bpm;
  const lines = source.split("\n");

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const rawLine = lines[lineIndex];
    const value = rawLine.trim();
    if (!value) continue;
    const position = { line: lineIndex + 1, column: rawLine.indexOf(value) + 1 };
    const found = value.match(/^(.+?)\s*\/\s*(\d+)\s*ms$/);
    if (!found) {
      return { error: { message: "请使用“按键组合 / 正整数ms”格式，例如 Z / 500ms。", ...position } };
    }

    const input = found[1].trim();
    const durationMs = Number(found[2]);
    if (!Number.isSafeInteger(durationMs) || durationMs <= 0) {
      return { error: { message: "时值必须是正整数毫秒。", ...position } };
    }

    if (input === "等待") {
      notes.push({ note: "0", key: null, modifier: null, isRest: true, beats: durationMs / beatMs, ...position });
      continue;
    }

    const parts = input.split(/\s*\+\s*/).map((part) => part.trim());
    if (!parts.length || parts.some((part) => !part)) {
      return { error: { message: "按键组合中的“+”两侧都必须有内容。", ...position } };
    }
    const keyToken = parts.at(-1).toLowerCase();
    const note = KEY_TO_NOTE[keyToken];
    if (!note) {
      return { error: { message: "按键只能使用 Z、X、C、V、B、N、M 或英文逗号 ,。", ...position } };
    }
    const modifierTokens = parts.slice(0, -1);
    const modifiers = modifierTokens.map((label) => KEYBOARD_LABEL_TO_MODIFIER[label]);
    if (modifiers.some((modifier) => !modifier)) {
      return { error: { message: "变调键只能使用“左键”、“中键”或“右键”，且必须写在键盘按键前。", ...position } };
    }
    if (new Set(modifiers).size !== modifiers.length || (modifiers.includes("L") && modifiers.includes("R"))) {
      return { error: { message: "变调键不能重复，也不能同时使用左键与右键。", ...position } };
    }
    const modifier = ["L", "M", "R"].filter((candidate) => modifiers.includes(candidate)).join("") || null;
    notes.push({ note, key: NOTE_KEYS[note], modifier, isRest: false, beats: durationMs / beatMs, ...position });
  }

  if (!notes.length) return { error: { message: "请至少输入一项按键或等待时值。", line: 1, column: 1 } };
  return enrichNotes(notes, bpm);
}

function readMidiText(bytes) {
  if (!bytes?.length) return "";
  try { return new TextDecoder("utf-8", { fatal: false }).decode(bytes).replace(/\0/g, "").trim(); } catch {}
  return Array.from(bytes, (byte) => String.fromCharCode(byte)).join("").replace(/\0/g, "").trim();
}

function midiKeySignature(sharpsFlats, isMinor) {
  const majorKeys = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"];
  const minorKeys = ["Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#"];
  const index = Math.max(0, Math.min(14, sharpsFlats + 7));
  return `1=${(isMinor ? minorKeys : majorKeys)[index]}`;
}

function midiMedian(values) {
  if (!values.length) return 0;
  const ordered = [...values].sort((left, right) => left - right);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}

function parseMidiData(buffer) {
  const bytes = new Uint8Array(buffer);
  if (bytes.length < 14 || readMidiText(bytes.slice(0, 4)) !== "MThd") throw new Error("这不是有效的标准 MIDI 文件。");
  const readU16 = (offset) => (bytes[offset] << 8) | bytes[offset + 1];
  const readU32 = (offset) => ((bytes[offset] * 0x1000000) + (bytes[offset + 1] << 16) + (bytes[offset + 2] << 8) + bytes[offset + 3]) >>> 0;
  const headerLength = readU32(4);
  if (headerLength < 6 || 8 + headerLength > bytes.length) throw new Error("MIDI 文件头损坏。");
  const division = readU16(12);
  if (division & 0x8000) throw new Error("暂不支持 SMPTE 时间码 MIDI，请先另存为常规节拍（PPQN）MIDI。");
  if (!division) throw new Error("MIDI 的节拍分辨率无效。");
  const trackCount = readU16(10);
  const tempos = [];
  const meters = [];
  const keys = [];
  const tracks = [];
  const ignoredInvalidNonNoteEvents = { controller: 0, program: 0, other: 0 };
  let offset = 8 + headerLength;

  function readVariable(cursor, end) {
    let value = 0;
    for (let count = 0; count < 4; count += 1) {
      if (cursor >= end) throw new Error("MIDI 事件被意外截断。");
      const byte = bytes[cursor++];
      value = (value << 7) | (byte & 0x7f);
      if (!(byte & 0x80)) return { value, cursor };
    }
    throw new Error("MIDI 事件长度无效。");
  }

  for (let trackIndex = 0; trackIndex < trackCount && offset + 8 <= bytes.length; trackIndex += 1) {
    const chunkType = readMidiText(bytes.slice(offset, offset + 4));
    const chunkLength = readU32(offset + 4);
    const start = offset + 8;
    const end = start + chunkLength;
    if (end > bytes.length) throw new Error("MIDI 音轨数据被意外截断。");
    offset = end;
    if (chunkType !== "MTrk") continue;
    let cursor = start;
    let tick = 0;
    let runningStatus = null;
    let name = "";
    const active = new Map();
    const notes = [];
    while (cursor < end) {
      const delta = readVariable(cursor, end);
      tick += delta.value;
      cursor = delta.cursor;
      if (cursor >= end) throw new Error("MIDI 事件缺少状态字节。");
      let status = bytes[cursor++];
      let firstData = null;
      if (status < 0x80) {
        if (!runningStatus) throw new Error("MIDI 的运行状态无效。 ");
        firstData = status;
        status = runningStatus;
      }
      if (status === 0xff) {
        if (cursor >= end) throw new Error("MIDI 元事件损坏。");
        const type = bytes[cursor++];
        const length = readVariable(cursor, end);
        cursor = length.cursor;
        if (cursor + length.value > end) throw new Error("MIDI 元事件被意外截断。");
        const data = bytes.slice(cursor, cursor + length.value);
        cursor += length.value;
        if (type === 0x03 && !name) name = readMidiText(data);
        if (type === 0x51 && data.length === 3) tempos.push({ tick, value: (data[0] << 16) | (data[1] << 8) | data[2], trackIndex });
        if (type === 0x58 && data.length >= 2) meters.push({ tick, numerator: data[0], denominator: 2 ** data[1], trackIndex });
        if (type === 0x59 && data.length >= 2) keys.push({ tick, sharpsFlats: data[0] > 127 ? data[0] - 256 : data[0], isMinor: data[1] === 1, trackIndex });
        continue;
      }
      if (status === 0xf0 || status === 0xf7) {
        const length = readVariable(cursor, end);
        cursor = length.cursor + length.value;
        if (cursor > end) throw new Error("MIDI 系统事件被意外截断。");
        continue;
      }
      if (status < 0x80 || status > 0xef) throw new Error("MIDI 包含不支持的系统事件。");
      runningStatus = status;
      const type = status & 0xf0;
      const channel = status & 0x0f;
      const dataLength = type === 0xc0 || type === 0xd0 ? 1 : 2;
      const data1 = firstData ?? bytes[cursor++];
      if (data1 === undefined || (dataLength === 2 && cursor >= end)) throw new Error("MIDI 通道事件被意外截断。");
      const data2 = dataLength === 2 ? bytes[cursor++] : 0;
      if (data1 > 127 || data2 > 127) {
        if (type === 0x80 || type === 0x90) throw new Error("MIDI 音符事件数据无效。");
        if (type === 0xb0) ignoredInvalidNonNoteEvents.controller += 1;
        else if (type === 0xc0) ignoredInvalidNonNoteEvents.program += 1;
        else ignoredInvalidNonNoteEvents.other += 1;
        continue;
      }
      if (type !== 0x80 && type !== 0x90) continue;
      const noteKey = `${channel}:${data1}`;
      if (type === 0x90 && data2 > 0) {
        const pending = active.get(noteKey) || [];
        pending.push({ start: tick, midi: data1, channel });
        active.set(noteKey, pending);
      } else {
        const pending = active.get(noteKey);
        const started = pending?.shift();
        if (!pending?.length) active.delete(noteKey);
        if (started && tick > started.start) notes.push({ ...started, end: tick });
      }
    }
    tracks.push({ name, notes });
  }
  if (!tracks.length) throw new Error("MIDI 文件中没有可读取的音轨。");
  return { division, tracks, tempos, meters, keys, ignoredInvalidNonNoteEvents };
}

function selectMidiMelodyTrack(tracks) {
  const candidates = tracks.map((track, index) => ({ ...track, index, notes: track.notes.filter((note) => note.channel !== 9) })).filter((track) => track.notes.length);
  if (!candidates.length) throw new Error("MIDI 中没有可演奏的非打击乐音符。");
  return candidates.map((track) => {
    const starts = new Set(track.notes.map((note) => note.start)).size;
    const median = midiMedian(track.notes.map((note) => note.midi));
    const monophonicRatio = starts / track.notes.length;
    return { ...track, rank: track.notes.length * (0.6 + monophonicRatio) + median / 3 };
  }).sort((left, right) => right.rank - left.rank || right.notes.length - left.notes.length || right.index - left.index)[0];
}

function midiTrackCandidates(tracks) {
  return tracks.map((track, index) => ({ ...track, index, notes: track.notes.filter((note) => note.channel !== 9) })).filter((track) => track.notes.length);
}

function midiDurationTicks(parsed) {
  return Math.max(parsed.division, ...parsed.tracks.flatMap((track) => track.notes.map((note) => note.end)), ...parsed.tempos.map((tempo) => tempo.tick), ...parsed.meters.map((meter) => meter.tick));
}

function chooseMidiTranspose(notes) {
  const playable = new Set(PLAYABLE_PITCHES.map((item) => item.midi));
  const median = midiMedian(notes.map((note) => note.midi));
  return [-36, -24, -12, 0, 12, 24, 36].map((shift) => {
    const covered = notes.filter((note) => playable.has(note.midi + shift)).length;
    return { shift, rank: covered * 100 - Math.abs(shift) * 3 - Math.abs(median + shift - 66) * 0.2 };
  }).sort((left, right) => right.rank - left.rank || Math.abs(left.shift) - Math.abs(right.shift))[0].shift;
}

function collapseMidiChords(notes, division) {
  const chordWindowTicks = Math.max(1, Math.round(division / 64));
  const ordered = [...notes].sort((left, right) => left.start - right.start || right.midi - left.midi || right.end - left.end);
  const melody = [];
  let chord = [];
  const flush = () => {
    if (!chord.length) return;
    melody.push([...chord].sort((left, right) => right.midi - left.midi || right.end - left.end)[0]);
    chord = [];
  };
  ordered.forEach((note) => {
    if (chord.length && note.start - chord[0].start > chordWindowTicks) flush();
    chord.push(note);
  });
  flush();
  return { notes: melody, collapsedNotes: Math.max(0, notes.length - melody.length) };
}

function midiToSequence(parsed, { trackIndex = null, startTick = 0, endTick = null } = {}) {
  const candidates = midiTrackCandidates(parsed.tracks);
  if (!candidates.length) throw new Error("MIDI 中没有可演奏的非打击乐音符。");
  const track = trackIndex === null ? selectMidiMelodyTrack(parsed.tracks) : candidates.find((candidate) => candidate.index === trackIndex);
  if (!track) throw new Error("所选 MIDI 音轨没有可演奏的非打击乐音符。");
  const durationTicks = midiDurationTicks(parsed);
  const from = Math.max(0, Math.min(durationTicks - 1, Math.round(startTick)));
  const to = Math.max(from + 1, Math.min(durationTicks, Math.round(endTick ?? durationTicks)));
  const sourceNotes = track.notes.filter((note) => note.end > from && note.start < to).map((note) => ({
    ...note,
    start: Math.max(note.start, from) - from,
    end: Math.min(note.end, to) - from
  }));
  if (!sourceNotes.length) throw new Error("所选音轨在这个截取范围内没有可转换的音符。");
  const collapsed = collapseMidiChords(sourceNotes, parsed.division);
  const melody = collapsed.notes;
  const transpose = chooseMidiTranspose(melody);
  const notes = [];
  const ticksToBeats = (ticks) => Math.round((ticks / parsed.division) * 1000000) / 1000000;
  let cursor = 0;
  melody.forEach((source, index) => {
    const start = Math.max(cursor, source.start);
    if (start > cursor) notes.push({ note: "0", modifier: null, beats: ticksToBeats(start - cursor), line: Math.floor(notes.length / 8) + 1 });
    const nextStart = melody[index + 1]?.start;
    const end = nextStart ? Math.min(source.end, Math.max(start + 1, nextStart)) : source.end;
    const midi = source.midi + transpose;
    const mapped = PLAYABLE_PITCHES.find((candidate) => candidate.midi === midi);
    if (mapped) notes.push({ note: mapped.note, modifier: mapped.modifier, beats: ticksToBeats(Math.max(1, end - start)), line: Math.floor(notes.length / 8) + 1 });
    cursor = Math.max(cursor, end);
  });
  if (!notes.length) throw new Error("MIDI 主旋律没有落在可转换的音域内。");
  const firstTempo = [...parsed.tempos].sort((left, right) => left.tick - right.tick || left.trackIndex - right.trackIndex)[0]?.value || 500000;
  const bpm = Math.max(30, Math.min(300, Math.round(60000000 / firstTempo)));
  const sequence = enrichNotes(notes, bpm);
  if (sequence.error) throw new Error(sequence.error.message);
  const meter = [...parsed.meters].sort((left, right) => left.tick - right.tick || left.trackIndex - right.trackIndex)[0];
  const key = [...parsed.keys].sort((left, right) => left.tick - right.tick || left.trackIndex - right.trackIndex)[0];
  return {
    sequence,
    bpm,
    meter: meter ? `${meter.numerator}/${meter.denominator}` : "4/4",
    key: key ? midiKeySignature(key.sharpsFlats, key.isMinor) : "1=C",
    trackName: track.name,
    selectedNotes: melody.length,
    sourceNoteCount: sourceNotes.length,
    startTick: from,
    endTick: to,
    collapsedChordNotes: collapsed.collapsedNotes,
    ignoredInvalidNonNoteEvents: parsed.ignoredInvalidNonNoteEvents,
    transpose,
    hasTempoChanges: parsed.tempos.length > 1
  };
}

function smoothMidiSequence(sequence, bpm) {
  const notes = sequence.notes.map((item) => ({ note: item.note, modifier: item.modifier, beats: item.beats, line: item.line }));
  let connectedGaps = 0;
  notes.forEach((item, index) => {
    const previous = notes[index - 1];
    const next = notes[index + 1];
    if (item.note !== "0" || !previous || previous.note === "0" || !next || next.note === "0" || item.beats > 1) return;
    const breathBeats = Math.min(item.beats, 0.04);
    previous.beats += item.beats - breathBeats;
    item.beats = breathBeats;
    connectedGaps += 1;
  });
  const smoothed = enrichNotes(notes, bpm);
  if (smoothed.error) throw new Error(smoothed.error.message);
  return { sequence: smoothed, connectedGaps };
}

function describeIgnoredMidiEvents(events = {}) {
  const descriptions = [];
  if (events.controller) descriptions.push(`${events.controller} 个无效控制器事件`);
  if (events.program) descriptions.push(`${events.program} 个无效程序切换事件`);
  if (events.other) descriptions.push(`${events.other} 个无效非音符事件`);
  return descriptions.length ? ` · 已忽略 ${descriptions.join("、")}` : "";
}

function midiStartBpm(parsed) {
  const tempo = [...parsed.tempos].sort((left, right) => left.tick - right.tick || left.trackIndex - right.trackIndex)[0]?.value || 500000;
  return Math.max(30, Math.min(300, Math.round(60000000 / tempo)));
}

function midiTickToTime(parsed, tick) {
  return formatTime((Math.max(0, tick) / parsed.division) * (60000 / midiStartBpm(parsed)));
}

function midiPitchLabel(midi) {
  const names = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
  return `${names[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`;
}

function midiTrackBounds(parsed, trackIndex, durationTicks = midiDurationTicks(parsed)) {
  const notes = parsed.tracks[trackIndex]?.notes.filter((note) => note.channel !== 9) || [];
  if (!notes.length) return { startTick: 0, endTick: durationTicks };
  return {
    startTick: Math.min(...notes.map((note) => note.start)),
    endTick: Math.max(...notes.map((note) => note.end))
  };
}

function resetMidiTrackPicker() {
  midiImportState = null;
  elements.midiTrackPicker.hidden = true;
  elements.midiTrackList.innerHTML = "";
}

function updateMidiRangeUi() {
  if (!midiImportState) return;
  const { parsed, durationTicks } = midiImportState;
  let startTick = Number(elements.midiRangeStartInput.value);
  let endTick = Number(elements.midiRangeEndInput.value);
  if (startTick >= endTick) {
    if (document.activeElement === elements.midiRangeStartInput) startTick = Math.max(0, endTick - 1);
    else endTick = Math.min(durationTicks, startTick + 1);
  }
  midiImportState.startTick = startTick;
  midiImportState.endTick = endTick;
  elements.midiRangeStartInput.value = startTick;
  elements.midiRangeEndInput.value = endTick;
  const left = (startTick / durationTicks) * 100;
  const width = ((endTick - startTick) / durationTicks) * 100;
  const windowBar = elements.midiRangeSliders.querySelector(".midi-range-window");
  windowBar.style.left = `${left}%`;
  windowBar.style.width = `${width}%`;
  elements.midiRangeStart.textContent = `开始 ${midiTickToTime(parsed, startTick)}`;
  elements.midiRangeEnd.textContent = `结束 ${midiTickToTime(parsed, endTick)}`;
  elements.midiRangeSummary.textContent = `截取 ${midiTickToTime(parsed, endTick - startTick)}`;
}

function renderMidiTrackPicker() {
  if (!midiImportState) return;
  const { parsed, selectedTrackIndex, durationTicks } = midiImportState;
  const playableTracks = midiTrackCandidates(parsed.tracks);
  const tracks = parsed.tracks.map((track, index) => ({ ...track, index, playableNotes: track.notes.filter((note) => note.channel !== 9) }));
  const pitches = tracks.flatMap((track) => track.notes.map((note) => note.midi));
  const lowestPitch = Math.floor((Math.min(...pitches) - 2) / 12) * 12;
  const highestPitch = Math.ceil((Math.max(...pitches) + 2) / 12) * 12;
  const pitchSpan = Math.max(12, highestPitch - lowestPitch);
  elements.midiTrackPicker.hidden = false;
  const rangeHint = midiImportState.rangeAutoTrimmed ? "已自动裁去所选轨首尾空白" : "已手动调整范围";
  elements.midiPickerStatus.textContent = `${tracks.length} 条音轨 · ${playableTracks.length} 条可转换 · ${rangeHint}`;
  elements.midiTrackList.innerHTML = tracks.map((track) => {
    const noteBars = track.notes.map((note) => {
      const left = (note.start / durationTicks) * 100;
      const width = Math.max(.35, ((note.end - note.start) / durationTicks) * 100);
      const top = Math.max(2, Math.min(94, ((highestPitch - note.midi) / pitchSpan) * 100));
      return `<i style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;top:${top.toFixed(3)}%"></i>`;
    }).join("");
    const label = track.name || `音轨 ${String(track.index + 1).padStart(2, "0")}`;
    const selectable = track.playableNotes.length > 0;
    const noteDescription = selectable ? `${track.playableNotes.length} 个可转换音符` : track.notes.length ? "仅打击乐，无法转换" : "无音符";
    return `<button class="midi-track" data-midi-track-index="${track.index}" type="button" role="radio" aria-checked="${selectable && track.index === selectedTrackIndex}" aria-label="选择 ${escapeHtml(label)}，${noteDescription}"${selectable ? "" : " disabled"}><span class="midi-track-index">${String(track.index + 1).padStart(2, "0")}</span><span class="midi-track-name">${escapeHtml(label)}<small>${noteDescription}</small></span><span class="midi-track-bar" aria-hidden="true"><b>${midiPitchLabel(highestPitch)}</b>${noteBars}<b>${midiPitchLabel(lowestPitch)}</b></span><span class="midi-track-count">${track.notes.length} NOTES</span></button>`;
  }).join("");
  [elements.midiRangeStartInput, elements.midiRangeEndInput].forEach((input) => {
    input.max = durationTicks;
    input.value = input === elements.midiRangeStartInput ? midiImportState.startTick : midiImportState.endTick;
  });
  updateMidiRangeUi();
}

function openMidiTrackPicker(file, parsed) {
  const defaultTrack = selectMidiMelodyTrack(parsed.tracks);
  const durationTicks = midiDurationTicks(parsed);
  const bounds = midiTrackBounds(parsed, defaultTrack.index, durationTicks);
  midiImportState = { file, parsed, title: file.name.replace(/\.(?:mid|midi)$/i, "").trim() || "MIDI 导入曲目", selectedTrackIndex: defaultTrack.index, durationTicks, ...bounds, rangeAutoTrimmed: true };
  renderMidiTrackPicker();
  elements.midiTrackPicker.scrollIntoView({ behavior: "smooth", block: "nearest" });
  toast("请选择需要转换的音轨与片段，然后点击“确定并生成谱子”。");
}

function formatTime(milliseconds) {
  const ms = Math.max(0, Math.round(milliseconds));
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
}

const editorLineNumberPairs = [
  [elements.score, elements.lineNumbers],
  [elements.jianpuScore, elements.jianpuLineNumbers],
  [elements.keyboardScore, elements.keyboardLineNumbers]
];

function syncLineNumbers(textarea, gutter) {
  if (!textarea || !gutter) return;
  if (gutter.scrollTop !== textarea.scrollTop) gutter.scrollTop = textarea.scrollTop;
}

function updateLineNumbers() {
  editorLineNumberPairs.forEach(([textarea, gutter]) => {
    const lines = Math.max(1, textarea.value.split("\n").length);
    gutter.textContent = Array.from({ length: lines }, (_, index) => index + 1).join("\n");
    syncLineNumbers(textarea, gutter);
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
}

function parseLegacyDetail(detail = "") {
  const parts = String(detail).split(" · ").map((part) => part.trim()).filter(Boolean);
  const key = parts.find((part) => /^(?:1=)?[A-G](?:[#b♯♭])?$/i.test(part)) || "调待补";
  const meter = parts.find((part) => /^\d{1,2}\/\d{1,2}$/.test(part)) || "拍号待补";
  const bpmIndex = parts.findIndex((part) => /^\d{2,3}\s*BPM$/i.test(part));
  const artist = bpmIndex >= 0
    ? parts.slice(bpmIndex + 1).filter((part) => !/^自动移调/.test(part)).join(" · ")
    : "";
  return { key, meter, artist };
}

function normalizeSong(song) {
  const builtin = BUILTIN_SONG_METADATA[song.title] || {};
  const legacy = parseLegacyDetail(song.detail);
  return {
    ...song,
    title: String(song.title || "未命名曲目").trim() || "未命名曲目",
    artist: String(song.artist || builtin.artist || legacy.artist || "未署名").trim() || "未署名",
    sharedBy: String(song.sharedBy || "Jiko").trim() || "Jiko",
    key: String(song.key || builtin.key || legacy.key || "调待补").trim() || "调待补",
    meter: String(song.meter || builtin.meter || legacy.meter || "拍号待补").trim() || "拍号待补",
    bpm: Number(song.bpm) || 120
  };
}

function renderSongLibrary(query = "") {
  elements.libraryCount.textContent = `${SONG_LIBRARY.length} TRACK${SONG_LIBRARY.length === 1 ? "" : "S"}`;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const songs = SONG_LIBRARY.map((song, index) => ({ ...song, index })).filter((song) => `${song.title} ${song.artist} ${song.sharedBy} ${song.key} ${song.meter} ${song.bpm}`.toLocaleLowerCase().includes(normalizedQuery));
  elements.songGrid.innerHTML = songs.length ? songs.map((song) => `
    <article class="song-card" data-song-index="${song.index}" data-index="${String(song.index + 1).padStart(2, "0")}">
      <button class="song-card-main" data-song-action="edit" type="button" aria-label="编辑《${escapeHtml(song.title)}》">
      <span class="song-number">TRACK ${String(song.index + 1).padStart(2, "0")}</span>
      <h3>${escapeHtml(song.title)}</h3>
      <p class="song-artist">${escapeHtml(song.artist)}</p>
      <div class="song-meta"><span>${escapeHtml(song.key)}</span><span>${escapeHtml(song.meter)}</span><span>${escapeHtml(song.bpm)} BPM</span></div>
      <span class="song-share">共享：${escapeHtml(song.sharedBy)}</span>
      </button>
      <div class="song-card-actions" aria-label="曲目操作">
        <button class="song-card-action" data-song-action="edit" type="button">编辑</button>
        <button class="song-card-action export" data-song-action="export" type="button">导出</button>
      </div>
    </article>
  `).join("") : '<p class="library-empty">没有匹配的曲目，换个关键词试试。</p>';
}

function beatsToJianpu(beats) {
  const known = new Map([[0.25, "__"], [0.375, "__."], [0.5, "_"], [0.75, "_."], [1, ""], [1.5, "."], [1.75, ".."], [2, "-"], [2.5, ".-"], [3, "--"], [4, "---"]]);
  return known.get(beats) ?? `:${formatRecordedBeat(beats)}`;
}

function jianpuPitch(note, modifier) {
  if (note === "0") return "0";
  return modifier === "LM" || modifier === "ML" ? `#,${note}` : modifier === "RM" || modifier === "MR" ? `#${note}'` : modifier === "M" ? `#${note}` : modifier === "L" ? `,${note}` : modifier === "R" ? `${note}'` : note;
}

function preciseToJianpu(source) {
  return source.split("\n").map((line) => line.split(/\s+/).filter(Boolean).map((token) => {
    if (token === "|") return token;
    const found = token.match(/^([LMR]{0,2})(0|1'|[1-7])\/(\d+(?:\.\d+)?)$/i);
    if (!found) return token;
    const modifier = found[1].toUpperCase();
    const note = found[2];
    const beats = Number(found[3]);
    const pitch = jianpuPitch(note, modifier);
    const rhythm = beatsToJianpu(beats);
    return `${pitch}${rhythm}`;
  }).join(" ")).join("\n");
}

function serializeSequence(sequence, formatItem) {
  const lines = [];
  sequence.notes.forEach((item) => {
    const lineIndex = Math.max(0, (item.line || 1) - 1);
    if (!lines[lineIndex]) lines[lineIndex] = [];
    lines[lineIndex].push(formatItem(item));
  });
  return lines.filter(Boolean).map((line) => `${line.join(" ")} |`).join("\n");
}

function sequenceToPrecise(sequence) {
  return serializeSequence(sequence, (item) => `${item.modifier || ""}${item.note}/${formatRecordedBeat(item.beats)}`);
}

function sequenceToJianpu(sequence) {
  return serializeSequence(sequence, (item) => `${jianpuPitch(item.note, item.modifier)}${beatsToJianpu(item.beats)}`);
}

function keyboardLabel(item) {
  if (item.isRest) return "等待";
  const modifiers = [...(item.modifier || "")].map((modifier) => KEYBOARD_MODIFIER_LABELS[modifier]);
  return [...modifiers, item.key.toUpperCase()].join(" + ");
}

function sequenceToKeyboard(sequence) {
  return sequence.notes.map((item) => `${keyboardLabel(item)} / ${item.durationMs}ms`).join("\n");
}

function syncSequenceToEditors(sequence, { except = null } = {}) {
  if (except !== "jianpu") elements.jianpuScore.value = sequenceToJianpu(sequence);
  const precise = sequenceToPrecise(sequence);
  if (except !== "precise") elements.score.value = precise;
  if (except !== "record") elements.recordedScore.value = precise;
  if (except !== "keyboard") elements.keyboardScore.value = sequenceToKeyboard(sequence);
  updateLineNumbers();
}

function loadSong(song, { destination = "editor" } = {}) {
  stopPreview();
  finishRecording({ apply: false });
  lastMidiFile = null;
  resetMidiTrackPicker();
  elements.macroName.value = song.title;
  elements.artistName.value = song.artist || "";
  elements.keySignature.value = song.key || "1=C";
  elements.timeSignature.value = song.meter || "4/4";
  elements.bpm.value = song.bpm;
  currentScoreCredit = { artist: song.artist || "", sharedBy: song.sharedBy || "" };
  const sequence = song.jianpu ? parseJianpu(song.jianpu, song.bpm) : parseScore(song.score, song.bpm);
  if (sequence.error) {
    toast(`《${song.title}》的曲库数据无法载入。`);
    return;
  }
  sequence.notes.forEach((item, index) => { item.index = index; });
  syncSequenceToEditors(sequence);
  [elements.jianpuScore, elements.score, elements.recordedScore, elements.keyboardScore].forEach((editor) => { editor.scrollTop = 0; });
  elements.jianpuLineNumbers.scrollTop = 0;
  elements.lineNumbers.scrollTop = 0;
  elements.keyboardLineNumbers.scrollTop = 0;
  setInputMode("jianpu", { force: true, silent: true });
  elements.jianpuScore.focus();
  syncLineNumbers(elements.jianpuScore, elements.jianpuLineNumbers);
  if (destination === "export") elements.macroExportSection.scrollIntoView({ behavior: "smooth", block: "start" });
  else document.querySelector(".workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
  toast(`已载入《${song.title}》· ${song.bpm} BPM。`);
}

const MODE_LABELS = { jianpu: "简谱模式", record: "录制模式", precise: "精确模式", keyboard: "三角洲键盘模式" };

function setInputMode(mode, { force = false, silent = false } = {}) {
  if (!MODE_LABELS[mode]) return false;
  if (mode === inputMode && !force) return true;
  if (inputMode === "record" && mode !== "record" && recording) finishRecording({ apply: true });
  stopPreview();
  if (!force) {
    const sequence = convert();
    if (!sequence) {
      toast("当前谱子有错误，修正后才能切换模式。");
      return false;
    }
    syncSequenceToEditors(sequence, { except: inputMode });
  }
  inputMode = mode;
  elements.inputPanes.forEach((pane) => { pane.hidden = pane.dataset.inputPane !== mode; });
  elements.inputModeButtons.forEach((button) => {
    const active = button.dataset.inputMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  const sequence = convert();
  if (sequence) elements.status.textContent = `已同步 · ${MODE_LABELS[mode]}`;
  if (!silent && sequence) toast(`已转换为${MODE_LABELS[mode]}，曲谱内容保持同步。`);
  return Boolean(sequence);
}

function formatRecordedBeat(value) {
  const rounded = Math.round(Number(value) * 1000000) / 1000000;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded).replace(/0+$/, "").replace(/\.$/, "");
}

function quantizeRecordedBeat(rawBeat) {
  const safeBeat = Math.max(0.1, Math.min(4, rawBeat));
  return RECORD_BEATS.reduce((closest, candidate) => Math.abs(candidate - safeBeat) < Math.abs(closest - safeBeat) ? candidate : closest, RECORD_BEATS[0]);
}

function updateRecordUi() {
  const isRecording = Boolean(recording);
  const count = recording?.events.length || 0;
  const holding = Boolean(recording?.activePress);
  elements.recordToggle.classList.toggle("live", isRecording);
  elements.recordToggle.querySelector("span").textContent = isRecording ? "完成并写入谱子" : "开始录制";
  elements.recordState.textContent = isRecording ? "RECORDING" : "IDLE";
  elements.recordState.classList.toggle("live", isRecording);
  elements.recordCount.textContent = isRecording ? `已录入 ${count} 个音符${holding ? " · 正在按住" : ""}` : "尚未录入音符";
}

function beginRecording() {
  stopPreview();
  releaseLiveRecordingVoice();
  recording = { events: [], startedAt: performance.now(), activePress: null };
  updateRecordUi();
  toast("录制开始：按住 Z–M、, 或页面琴键；松开即结束，直接按下一音会自动切换。 ");
}

function scoreFromRecording(events, bpm) {
  const beatMs = 60000 / bpm;
  const durations = events.map((event) => quantizeRecordedBeat((event.durationMs || beatMs * 0.25) / beatMs));
  const tokens = events.map((event, index) => `${event.modifier}${event.note}/${formatRecordedBeat(durations[index])}`);
  return tokens.reduce((lines, token, index) => {
    const lineIndex = Math.floor(index / 8);
    lines[lineIndex] = lines[lineIndex] ? `${lines[lineIndex]} ${token}` : token;
    return lines;
  }, []).join("\n");
}

function finishRecording({ apply = true } = {}) {
  if (!recording) return;
  finishActiveRecordPress();
  const captured = recording.events;
  releaseLiveRecordingVoice();
  recording = null;
  updateRecordUi();
  if (!apply) return;
  if (!captured.length) { toast("未录到音符，原谱子没有改动。 "); return; }
  elements.recordedScore.value = scoreFromRecording(captured, Number(elements.bpm.value));
  updateLineNumbers();
  const sequence = convert();
  if (sequence) {
    syncSequenceToEditors(sequence, { except: "record" });
    toast(`已写入 ${captured.length} 个音符，并同步到全部模式。`);
  }
  elements.recordedScore.focus();
}

function flashRecordedKey(note) {
  const button = [...elements.recordKeyboard.querySelectorAll("[data-record-note]")].find((key) => key.dataset.recordNote === note);
  if (!button) return;
  button.classList.add("hit");
  window.setTimeout(() => button.classList.remove("hit"), 125);
}

function finishActiveRecordPress(at = performance.now(), { releaseAudio = true } = {}) {
  if (!recording?.activePress) return;
  const event = recording.activePress;
  event.durationMs = Math.max(1, at - event.at);
  recording.activePress = null;
  if (releaseAudio) releaseLiveRecordingVoice();
  updateRecordUi();
}

function startRecordingNote(note, source) {
  if (!recording) { toast("请先点击“开始录制”。 "); return; }
  if (recording.activePress?.source === source) return;
  const now = performance.now();
  finishActiveRecordPress(now, { releaseAudio: false });
  const event = { note, modifier: selectedRecordModifier, at: now, source, durationMs: 0 };
  recording.events.push(event);
  recording.activePress = event;
  playLiveRecordingNote(note);
  flashRecordedKey(note);
  updateRecordUi();
}

function endRecordingNote(source) {
  if (recording?.activePress?.source !== source) return;
  finishActiveRecordPress();
}

function setValidation(message, type = "") {
  elements.validation.textContent = message;
  elements.validation.className = `validation ${type}`;
}

function setPreviewProgress(positionMs = 0, sequence = currentSequence) {
  const totalMs = sequence?.totalMs || 0;
  const safePosition = Math.max(0, Math.min(totalMs, Math.round(positionMs)));
  previewCursorMs = safePosition;
  elements.previewProgress.max = totalMs;
  elements.previewProgress.value = safePosition;
  elements.previewProgress.disabled = !totalMs;
  elements.previewProgressLabel.textContent = `${formatTime(safePosition)} / ${totalMs ? formatTime(totalMs) : "--:--.---"}`;
}

function highlightTimelinePosition(positionMs, { scroll = false } = {}) {
  const sequence = currentSequence;
  if (!sequence) return;
  const index = sequence.notes.findIndex((item) => positionMs >= item.timeMs && positionMs < item.timeMs + item.durationMs);
  clearTimelinePlayback();
  if (index < 0) return;
  const row = elements.timeline.querySelector(`[data-note-index="${index}"]`);
  row?.classList.add("playing");
  if (scroll) keepTimelineRowVisible(row);
}

function updateMonitor(sequence) {
  if (!sequence) {
    elements.totalTime.textContent = "--:--.---";
    elements.noteCount.textContent = "--";
    elements.eventCount.textContent = "--";
    elements.beatMs.textContent = "-- MS / BEAT";
    elements.timeline.innerHTML = '<li class="empty-state">转换后将在这里显示每个音符的按键时刻。</li>';
    elements.monitorDot.classList.remove("active");
    setPreviewProgress(0, null);
    return;
  }
  elements.totalTime.textContent = formatTime(sequence.totalMs);
  elements.noteCount.textContent = sequence.notes.length;
  elements.eventCount.textContent = sequence.events;
  elements.beatMs.textContent = `${sequence.beatMs} MS / BEAT`;
  elements.monitorDot.classList.add("active");
  elements.timeline.innerHTML = sequence.notes.map((item) => {
    const modifier = item.modifier ? `${item.modifier} + ` : "";
    const detail = item.isRest ? `休止 ${item.durationMs}ms` : `${modifier}${item.key.toUpperCase()} · 按住 ${item.pressMs}ms${item.waitMs ? ` · 气口 ${item.waitMs}ms` : ""}`;
    return `<li data-note-index="${item.index ?? 0}" data-time-ms="${item.timeMs}" tabindex="0" role="button" aria-label="跳转到 ${formatTime(item.timeMs)}，${escapeHtml(detail)}"><span class="time">${formatTime(item.timeMs)}</span><span class="timeline-key${item.isRest ? " rest" : item.modifier ? " modifier" : ""}">${item.isRest ? "休" : item.note}</span><span class="event-detail">${detail}</span></li>`;
  }).join("");
  setPreviewProgress(0, sequence);
}

function convert() {
  updateLineNumbers();
  const bpm = Number(elements.bpm.value);
  const sequence = inputMode === "jianpu"
    ? parseJianpu(elements.jianpuScore.value, bpm)
    : inputMode === "keyboard"
      ? parseKeyboardScore(elements.keyboardScore.value, bpm)
      : parseScore(inputMode === "record" ? elements.recordedScore.value : elements.score.value, bpm);
  if (sequence.error) {
    currentSequence = null;
    updateMonitor(null);
    elements.status.textContent = `错误 · ${sequence.error.line}:${sequence.error.column}`;
    setValidation(`第 ${sequence.error.line} 行，第 ${sequence.error.column} 列：${sequence.error.message}`, "error");
    return null;
  }
  sequence.notes.forEach((item, index) => { item.index = index; });
  currentSequence = sequence;
  updateMonitor(sequence);
  elements.status.textContent = "序列已就绪";
  setValidation(`校验通过 · ${sequence.notes.length} 个音符，预计播放 ${formatTime(sequence.totalMs)}。`, "success");
  return sequence;
}

function openKeyboardMacroDialog() {
  const sequence = convert();
  if (!sequence) {
    toast("请先修正谱子错误。");
    return;
  }
  elements.keyboardMacroTitle.textContent = `${elements.macroName.value.trim() || "当前曲谱"} · 手动输入宏`;
  elements.keyboardMacroMeta.textContent = `三角洲键盘模式 · ${sequence.notes.length} 个事件 · ${formatTime(sequence.totalMs)}`;
  elements.keyboardMacroOutput.value = sequenceToKeyboard(sequence);
  elements.keyboardMacroDialog.showModal();
}

function openSectionGuide(key) {
  const guide = SECTION_GUIDES[key];
  if (!guide) return;
  elements.sectionGuideWindowTitle.textContent = guide.windowTitle;
  elements.sectionGuideIndex.textContent = guide.index;
  elements.sectionGuideHeading.textContent = guide.title;
  elements.sectionGuideIntro.textContent = guide.intro;
  elements.sectionGuideSteps.innerHTML = guide.steps.map(([number, title, copy]) => `
    <article class="section-guide-step">
      <b>${number}</b>
      <div><h3>${title}</h3><p>${copy}</p></div>
    </article>
  `).join("");
  elements.sectionGuideDialog.showModal();
}

function handleBpmChange() {
  stopPreview();
  if (inputMode !== "keyboard" || !currentSequence) {
    convert();
    return;
  }
  const sequence = enrichNotes(currentSequence.notes, Number(elements.bpm.value));
  if (sequence.error) {
    elements.status.textContent = `错误 · ${sequence.error.line}:${sequence.error.column}`;
    setValidation(`第 ${sequence.error.line} 行，第 ${sequence.error.column} 列：${sequence.error.message}`, "error");
    return;
  }
  sequence.notes.forEach((item, index) => { item.index = index; });
  currentSequence = sequence;
  syncSequenceToEditors(sequence);
  updateMonitor(sequence);
  elements.status.textContent = "序列已就绪";
  setValidation(`校验通过 · ${sequence.notes.length} 个音符，预计播放 ${formatTime(sequence.totalMs)}。`, "success");
}

function getAudioEngine() {
  if (audioContext) return audioContext;
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) throw new Error("当前浏览器不支持音频试听。");
  audioContext = new Context();
  masterGain = audioContext.createGain();
  masterGain.gain.value = Number(elements.volume.value) / 100;
  const compressor = audioContext.createDynamicsCompressor();
  compressor.threshold.value = -18;
  compressor.knee.value = 12;
  compressor.ratio.value = 7;
  masterGain.connect(compressor).connect(audioContext.destination);
  return audioContext;
}

function wakeAudioEngine() {
  const context = getAudioEngine();
  if (context.state === "running") return Promise.resolve(context);
  return context.resume().then(() => {
    if (context.state !== "running") throw new Error("Safari 音频仍处于暂停状态，请再次点击试听按钮或取消标签页静音。");
    return context;
  });
}

function prewarmAudioEngine() {
  try {
    void wakeAudioEngine().catch((error) => toast(error.message || "无法启动音频试听。 "));
  } catch (error) {
    toast(error.message || "无法启动音频试听。 ");
  }
}

function previewFrequency(item) {
  const midi = macroMidi(item);
  return 440 * (2 ** ((midi - 69) / 12));
}

function getHarmonicaWave(context) {
  if (harmonicaWaveCache.has(context)) return harmonicaWaveCache.get(context);
  const real = new Float32Array(12);
  const imag = new Float32Array([0, 1, 0.42, 0.23, 0.14, 0.085, 0.052, 0.034, 0.022, 0.015, 0.01, 0.007]);
  const wave = context.createPeriodicWave(real, imag);
  harmonicaWaveCache.set(context, wave);
  return wave;
}

function getHarmonicaNoiseBuffer(context) {
  if (harmonicaNoiseCache.has(context)) return harmonicaNoiseCache.get(context);
  const length = Math.ceil(context.sampleRate * 0.35);
  const buffer = context.createBuffer(1, length, context.sampleRate);
  const data = buffer.getChannelData(0);
  let seed = 0x6d2b79f5;
  let filtered = 0;
  for (let index = 0; index < data.length; index += 1) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const white = (seed / 0xffffffff) * 2 - 1;
    filtered = filtered * 0.94 + white * 0.06;
    data[index] = (white * 0.3 + filtered * 0.7) * 0.6;
  }
  harmonicaNoiseCache.set(context, buffer);
  return buffer;
}

function createHarmonicaVoice(context, startAt, duration, frequency) {
  const gain = context.createGain();
  const toneFilter = context.createBiquadFilter();
  const resonance = context.createBiquadFilter();
  const reed = context.createOscillator();
  const reedColor = context.createOscillator();
  const reedGain = context.createGain();
  const colorGain = context.createGain();
  const breath = context.createBufferSource();
  const breathFilter = context.createBiquadFilter();
  const breathGain = context.createGain();
  const hasScheduledEnd = Number.isFinite(duration) && duration > 0;
  const endAt = hasScheduledEnd ? startAt + duration : null;
  const wave = getHarmonicaWave(context);
  const noiseBuffer = getHarmonicaNoiseBuffer(context);

  reed.setPeriodicWave(wave);
  reed.frequency.setValueAtTime(frequency, startAt);
  reed.detune.setValueAtTime(-2, startAt);
  reedColor.type = "sine";
  reedColor.frequency.setValueAtTime(frequency * 2.003, startAt);
  reedColor.detune.setValueAtTime(3, startAt);
  reedGain.gain.value = 0.78;
  colorGain.gain.value = 0.12;
  toneFilter.type = "lowpass";
  toneFilter.frequency.setValueAtTime(Math.min(6200, Math.max(2200, frequency * 10.5)), startAt);
  toneFilter.Q.value = 0.8;
  resonance.type = "peaking";
  resonance.frequency.setValueAtTime(Math.min(3400, Math.max(900, frequency * 2.2)), startAt);
  resonance.Q.value = 1.1;
  resonance.gain.setValueAtTime(3.5, startAt);
  breath.buffer = noiseBuffer;
  breath.loop = true;
  breathFilter.type = "bandpass";
  breathFilter.frequency.setValueAtTime(Math.min(5200, Math.max(1800, frequency * 3.6)), startAt);
  breathFilter.Q.value = 0.7;

  const attackAt = hasScheduledEnd ? Math.min(endAt - 0.008, startAt + 0.02) : startAt + 0.02;
  const sustainAt = hasScheduledEnd
    ? Math.min(endAt - 0.005, Math.max(attackAt + 0.005, startAt + 0.11))
    : startAt + 0.11;
  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(0.15, attackAt);
  if (sustainAt < endAt || !hasScheduledEnd) gain.gain.exponentialRampToValueAtTime(0.095, sustainAt);
  if (hasScheduledEnd) gain.gain.exponentialRampToValueAtTime(0.0001, endAt);
  breathGain.gain.setValueAtTime(0.0001, startAt);
  breathGain.gain.exponentialRampToValueAtTime(0.018, startAt + 0.012);
  breathGain.gain.exponentialRampToValueAtTime(0.006, hasScheduledEnd ? Math.min(endAt - 0.012, startAt + 0.09) : startAt + 0.09);
  if (hasScheduledEnd) breathGain.gain.exponentialRampToValueAtTime(0.0001, endAt);

  reed.connect(reedGain).connect(toneFilter);
  reedColor.connect(colorGain).connect(toneFilter);
  toneFilter.connect(resonance).connect(gain).connect(masterGain);
  breath.connect(breathFilter).connect(breathGain).connect(gain);
  reed.start(startAt);
  reedColor.start(startAt);
  breath.start(startAt);
  if (hasScheduledEnd) {
    reed.stop(endAt + 0.025);
    reedColor.stop(endAt + 0.025);
    breath.stop(endAt + 0.025);
  }
  return { context, gain, nodes: [reed, reedColor, breath] };
}

function scheduleHarmonicaTone(context, startAt, duration, frequency) {
  return createHarmonicaVoice(context, startAt, duration, frequency).nodes;
}

function releaseLiveRecordingVoice() {
  if (!liveRecordingVoice) return;
  const { context, gain, nodes } = liveRecordingVoice;
  const now = context.currentTime;
  gain.gain.cancelScheduledValues(now);
  gain.gain.setValueAtTime(0.1, now);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.025);
  nodes.forEach((node) => { try { node.stop(now + 0.045); } catch {} });
  liveRecordingVoice = null;
}

function playLiveRecordingNote(note) {
  try {
    const context = getAudioEngine();
    context.resume();
    masterGain.gain.setTargetAtTime(Number(elements.volume.value) / 100, context.currentTime, 0.01);
    const voice = createHarmonicaVoice(context, context.currentTime, null, previewFrequency({ note, modifier: selectedRecordModifier || null }));
    releaseLiveRecordingVoice();
    liveRecordingVoice = voice;
  } catch (error) {
    toast(error.message || "无法启动录制试听。 ");
  }
}

function clearTimelinePlayback() {
  elements.timeline.querySelectorAll(".playing").forEach((row) => row.classList.remove("playing"));
}

function keepTimelineRowVisible(row) {
  if (!row) return;
  const timelineRect = elements.timeline.getBoundingClientRect();
  const rowRect = row.getBoundingClientRect();
  if (rowRect.top < timelineRect.top || rowRect.bottom > timelineRect.bottom) {
    const centeredOffset = rowRect.top - timelineRect.top - (elements.timeline.clientHeight - rowRect.height) / 2;
    elements.timeline.scrollTop = Math.max(0, elements.timeline.scrollTop + centeredOffset);
  }
}

function setPreviewUi(state = "ready") {
  const isPlaying = state === "playing";
  const isPaused = state === "paused";
  const label = elements.previewButton.querySelector("span");
  const icon = elements.previewButton.querySelector("b");
  elements.previewButton.disabled = false;
  icon.textContent = isPlaying ? "Ⅱ" : "▶";
  label.textContent = isPlaying ? "暂停" : isPaused ? "继续" : "试听整段";
  elements.previewButton.setAttribute("aria-label", isPlaying ? "暂停试听" : isPaused ? "继续试听" : "试听整段简谱");
  elements.stopButton.disabled = !isPlaying && !isPaused;
  elements.previewState.textContent = isPlaying ? "PLAYING" : isPaused ? "PAUSED" : "READY";
  elements.previewState.classList.toggle("live", isPlaying);
}

function clearPreviewTimers(preview) {
  preview.timers.forEach((timer) => window.clearTimeout(timer));
  preview.timers = [];
}

function stopPreviewNodes(preview) {
  preview.nodes.forEach((node) => { try { node.stop(); } catch {} });
  preview.nodes.clear();
}

function clearPreviewScheduler(preview) {
  if (!preview.schedulerTimer) return;
  window.clearInterval(preview.schedulerTimer);
  preview.schedulerTimer = null;
}

function stopPreview({ resetProgress = true } = {}) {
  if (!activePreview) return;
  stopPreviewNodes(activePreview);
  clearPreviewTimers(activePreview);
  clearPreviewScheduler(activePreview);
  activePreview = null;
  window.cancelAnimationFrame(previewProgressFrame);
  clearTimelinePlayback();
  if (resetProgress) setPreviewProgress(0);
  setPreviewUi("ready");
}

function previewPositionMs(preview) {
  const elapsedMs = Math.max(0, (preview.context.currentTime - preview.startAt) * 1000);
  return Math.max(preview.positionMs, Math.min(preview.sequence.totalMs, preview.positionMs + elapsedMs));
}

function nextPreviewNoteIndex(sequence, positionMs) {
  const index = sequence.notes.findIndex((item) => item.timeMs + item.pressMs > positionMs);
  return index < 0 ? sequence.notes.length : index;
}

function updatePreviewTimeline(preview, positionMs) {
  const { notes } = preview.sequence;
  let index = preview.timelineIndex;
  if (!Number.isInteger(index) || positionMs < notes[index]?.timeMs || positionMs >= notes[index]?.timeMs + notes[index]?.durationMs) {
    index = notes.findIndex((item) => positionMs >= item.timeMs && positionMs < item.timeMs + item.durationMs);
  }
  if (index < 0 || index === preview.timelineIndex) return;
  preview.timelineIndex = index;
  clearTimelinePlayback();
  const row = elements.timeline.querySelector(`[data-note-index="${index}"]`);
  row?.classList.add("playing");
  keepTimelineRowVisible(row);
}

function registerPreviewNodes(preview, nodes) {
  nodes.forEach((node) => {
    preview.nodes.add(node);
    node.addEventListener("ended", () => preview.nodes.delete(node), { once: true });
  });
}

function schedulePreviewWindow(preview) {
  if (activePreview !== preview || preview.state !== "playing") return;
  const positionMs = previewPositionMs(preview);
  const windowEndMs = Math.min(preview.sequence.totalMs, positionMs + PREVIEW_SCHEDULE_AHEAD_MS);
  while (preview.nextNoteIndex < preview.sequence.notes.length) {
    const item = preview.sequence.notes[preview.nextNoteIndex];
    if (item.timeMs > windowEndMs) break;
    preview.nextNoteIndex += 1;
    const noteEnd = item.timeMs + item.pressMs;
    if (item.isRest || noteEnd <= preview.positionMs) continue;
    const skippedMs = Math.max(0, preview.positionMs - item.timeMs);
    const noteLength = Math.max(0.035, (item.pressMs - skippedMs) / 1000);
    const startAt = preview.startAt + Math.max(0, item.timeMs - preview.positionMs) / 1000;
    registerPreviewNodes(preview, scheduleHarmonicaTone(preview.context, startAt, noteLength, previewFrequency(item)));
  }
  if (positionMs >= preview.sequence.totalMs) stopPreview();
}

function startPreviewScheduler(preview) {
  schedulePreviewWindow(preview);
  preview.schedulerTimer = window.setInterval(() => schedulePreviewWindow(preview), PREVIEW_SCHEDULER_INTERVAL_MS);
}

function refreshPreviewProgress() {
  if (!activePreview || activePreview.state !== "playing") return;
  const position = previewPositionMs(activePreview);
  setPreviewProgress(position, activePreview.sequence);
  updatePreviewTimeline(activePreview, position);
  previewProgressFrame = window.requestAnimationFrame(refreshPreviewProgress);
}

async function pausePreview() {
  if (!activePreview || activePreview.state !== "playing") return;
  const preview = activePreview;
  const positionMs = previewPositionMs(preview);
  stopPreviewNodes(preview);
  clearPreviewScheduler(preview);
  window.cancelAnimationFrame(previewProgressFrame);
  try {
    await preview.context.suspend();
    preview.positionMs = positionMs;
    preview.nextNoteIndex = nextPreviewNoteIndex(preview.sequence, positionMs);
    setPreviewProgress(preview.positionMs, preview.sequence);
    preview.state = "paused";
    setPreviewUi("paused");
  } catch (error) {
    startPreviewScheduler(preview);
    toast(error.message || "无法暂停试听。 ");
  }
}

async function resumePreview() {
  if (!activePreview || activePreview.state !== "paused") return;
  const preview = activePreview;
  try {
    await preview.context.resume();
    preview.startAt = preview.context.currentTime;
    preview.state = "playing";
    preview.nextNoteIndex = nextPreviewNoteIndex(preview.sequence, preview.positionMs);
    startPreviewScheduler(preview);
    previewProgressFrame = window.requestAnimationFrame(refreshPreviewProgress);
    setPreviewUi("playing");
  } catch (error) {
    toast(error.message || "无法继续试听。 ");
  }
}

function togglePreview() {
  if (!activePreview) return playPreview(previewCursorMs);
  if (activePreview.state === "playing") return pausePreview();
  return resumePreview();
}

async function playPreview(positionMs = 0) {
  if (recording) { toast("请先完成录制，再播放谱子。 "); return; }
  const sequence = convert();
  if (!sequence) { toast("请先修正谱子错误。 "); return; }
  const startPosition = Math.max(0, Math.min(sequence.totalMs, Number(positionMs) || 0));
  stopPreview({ resetProgress: false });
  try {
    const context = await wakeAudioEngine();
    masterGain.gain.setTargetAtTime(Number(elements.volume.value) / 100, context.currentTime, 0.01);
    const startAt = context.currentTime + 0.045;
    activePreview = {
      context, nodes: new Set(), timers: [], schedulerTimer: null, sequence, startAt, positionMs: startPosition,
      state: "playing", nextNoteIndex: nextPreviewNoteIndex(sequence, startPosition), timelineIndex: -1
    };
    setPreviewProgress(startPosition, sequence);
    highlightTimelinePosition(startPosition);
    startPreviewScheduler(activePreview);
    window.cancelAnimationFrame(previewProgressFrame);
    previewProgressFrame = window.requestAnimationFrame(refreshPreviewProgress);
    setPreviewUi("playing");
  } catch (error) {
    stopPreview({ resetProgress: false });
    setPreviewUi("ready");
    toast(error.message || "无法启动试听。 ");
  }
}

function escapedXml(value) {
  return String(value).replace(/[<>&'\"]/g, (character) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[character]));
}

function safeName() {
  return (elements.macroName.value.trim() || "Delta Harmonica").replace(/[\\/:*?"<>|]/g, "-").slice(0, 48);
}

function makeUuid() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.random() * 16 | 0;
    return (character === "x" ? random : random & 3 | 8).toString(16);
  });
}

function setMacroTriggerValidation(message = "", invalidFields = []) {
  elements.macroTriggerValidation.textContent = message;
  elements.macroTriggerValidation.hidden = !message;
  elements.macroTriggerButton.setAttribute("aria-invalid", String(invalidFields.includes(elements.macroTriggerButton)));
  elements.macroStopButton.setAttribute("aria-invalid", String(invalidFields.includes(elements.macroStopButton)));
}

function clearMacroTriggerValidation() {
  setMacroTriggerValidation("");
}

function updateMacroTriggerHint() {
  const mode = elements.macroTriggerMode.value;
  elements.macroSettingsHint.textContent = MACRO_TRIGGER_MODE_HINTS[mode] || MACRO_TRIGGER_MODE_HINTS.once;
}

function readMacroTriggerSettings() {
  const rawButton = String(elements.macroTriggerButton.value).trim();
  const button = Number(rawButton);
  const rawStopButton = String(elements.macroStopButton.value).trim();
  const stopButton = rawStopButton ? Number(rawStopButton) : 0;
  const mode = elements.macroTriggerMode.value;
  if (!rawButton || !Number.isInteger(button) || button < 1 || button > 20) {
    setMacroTriggerValidation("请输入 1 到 20 之间的鼠标绑定键。", [elements.macroTriggerButton]);
    return null;
  }
  if (rawStopButton && (!Number.isInteger(stopButton) || stopButton < 1 || stopButton > 20)) {
    setMacroTriggerValidation("全局停止键必须是 1 到 20 之间的鼠标键，或留空禁用。", [elements.macroStopButton]);
    return null;
  }
  if (stopButton === button) {
    setMacroTriggerValidation("全局停止键不能单独填写为播放绑定键；如需同键开关，请留空并选择“切换播放”。", [elements.macroTriggerButton, elements.macroStopButton]);
    return null;
  }
  const pitchModifierButtons = new Set(Object.values(MOUSE_BUTTONS).map((modifier) => modifier.ghub));
  if (pitchModifierButtons.has(button) || pitchModifierButtons.has(stopButton)) {
    setMacroTriggerValidation("鼠标键 1、2、3 用于口琴变调，不能设为播放或停止键；请使用侧键 4–20。", [
      ...(pitchModifierButtons.has(button) ? [elements.macroTriggerButton] : []),
      ...(pitchModifierButtons.has(stopButton) ? [elements.macroStopButton] : [])
    ]);
    return null;
  }
  if (!Object.prototype.hasOwnProperty.call(MACRO_TRIGGER_MODE_LABELS, mode)) {
    setMacroTriggerValidation("请选择有效的触发模式。");
    return null;
  }
  clearMacroTriggerValidation();
  return { button, stopButton, mode };
}

function requireMacroTriggerSettings() {
  const settings = readMacroTriggerSettings();
  if (settings) return settings;
  elements.macroSettings.scrollIntoView({ behavior: "smooth", block: "center" });
  const invalidField = elements.macroStopButton.getAttribute("aria-invalid") === "true"
    ? elements.macroStopButton
    : elements.macroTriggerButton;
  invalidField.focus();
  toast("请先完成 G HUB 宏触发设置。 ");
  return null;
}

function generateLua(sequence, triggerSettings) {
  const { button, stopButton, mode } = triggerSettings;
  const lines = [
    "-- Harmonica Deck · Delta Force harmonica sequence",
    `-- Score: ${safeName()} | ${sequence.notes.length} notes | ${elements.bpm.value} BPM`,
    `-- Trigger: mouse button ${button} · ${MACRO_TRIGGER_MODE_LABELS[mode]}`,
    "-- once = play once; hold = play while the trigger is held; toggle = press to start and press again to stop.",
    "-- Stop handling releases the current note and any mouse modifier buttons.",
    `local TRIGGER_BUTTON = ${button}`,
    `local STOP_BUTTON = ${stopButton}`,
    `local TRIGGER_MODE = ${JSON.stringify(mode)}`,
    "local isPlaying = false",
    "local stopRequested = false",
    "local activeKey = nil",
    "local activeModifiers = {}",
    "local activePlaybackGeneration = 0",
    "local toggleTriggerArmed = false",
    "local playbackStartedAt = 0",
    "local playbackGeneration = 0",
    "",
    "local function ReleaseHeldInputs(ownerGeneration)",
    "  if ownerGeneration ~= nil and activePlaybackGeneration ~= ownerGeneration then return end",
    "  if activeKey ~= nil then",
    "    ReleaseKey(activeKey)",
    "    activeKey = nil",
    "  end",
    "  for index = #activeModifiers, 1, -1 do",
    "    ReleaseMouseButton(activeModifiers[index])",
    "  end",
    "  activeModifiers = {}",
    "  activePlaybackGeneration = 0",
    "end",
    "",
    "local function RequestStop()",
    "  playbackGeneration = playbackGeneration + 1",
    "  stopRequested = true",
    "  ReleaseHeldInputs()",
    "  isPlaying = false",
    "  playbackStartedAt = 0",
    "end",
    "",
    "local function StopButtonPressed()",
    "  return STOP_BUTTON > 0 and IsMouseButtonPressed(STOP_BUTTON)",
    "end",
    "",
    "-- Wait against absolute score time so driver call overhead cannot accumulate.",
    "local function WaitUntil(targetMs, ownerGeneration)",
    "  while true do",
    "    if stopRequested or playbackGeneration ~= ownerGeneration then return false end",
    "    if StopButtonPressed() then",
    "      RequestStop()",
    "      return false",
    "    end",
    "    if TRIGGER_MODE == \"toggle\" then",
    "      local triggerPressed = IsMouseButtonPressed(TRIGGER_BUTTON)",
    "      if not triggerPressed then",
    "        toggleTriggerArmed = true",
    "      elseif toggleTriggerArmed then",
    "        RequestStop()",
    "        return false",
    "      end",
    "    end",
    "    if TRIGGER_MODE == \"hold\" and not IsMouseButtonPressed(TRIGGER_BUTTON) then",
    "      RequestStop()",
    "      return false",
    "    end",
    "    local remaining = targetMs - (GetRunningTime() - playbackStartedAt)",
    "    if remaining <= 0 then return true end",
    "    local slice = math.min(remaining, 10)",
    "    Sleep(slice)",
    "  end",
    "end",
    "",
    "function PlayHarmonica()",
    "  if isPlaying then return end",
    "  playbackGeneration = playbackGeneration + 1",
    "  local ownerGeneration = playbackGeneration",
    "  isPlaying = true",
    "  stopRequested = false",
    "  toggleTriggerArmed = not IsMouseButtonPressed(TRIGGER_BUTTON)",
    "  playbackStartedAt = GetRunningTime()",
  ];
  sequence.notes.forEach((item, index) => {
    lines.push(`  if not WaitUntil(${item.timeMs}, ownerGeneration) then`);
    lines.push("    if playbackGeneration == ownerGeneration then stopRequested = true end");
    lines.push("  end");
    lines.push("  if not stopRequested and playbackGeneration == ownerGeneration then");
    lines.push(`    -- ${String(index + 1).padStart(2, "0")}: ${item.modifier ? `${item.modifier}+` : ""}${item.note}, ${item.beats} beat(s)`);
    if (item.isRest) {
      lines.push(`    if not WaitUntil(${item.timeMs + item.durationMs}, ownerGeneration) then`);
      lines.push("      if playbackGeneration == ownerGeneration then stopRequested = true end");
      lines.push("    end");
    } else {
      const modifierButtons = [...(item.modifier || "")].map((modifier) => MOUSE_BUTTONS[modifier].ghub);
      lines.push(`    activeModifiers = {${modifierButtons.join(", ")}}`);
      lines.push("    activePlaybackGeneration = ownerGeneration");
      lines.push("    for index = 1, #activeModifiers do");
      lines.push("      PressMouseButton(activeModifiers[index])");
      lines.push("    end");
      lines.push(`    activeKey = ${JSON.stringify(item.key)}`);
      lines.push("    PressKey(activeKey)");
      lines.push(`    if not WaitUntil(${item.timeMs + item.pressMs}, ownerGeneration) then`);
      lines.push("      if playbackGeneration == ownerGeneration then stopRequested = true end");
      lines.push("    end");
      lines.push("    ReleaseHeldInputs(ownerGeneration)");
    }
    lines.push("  end");
  });
  lines.push(
    "  if playbackGeneration == ownerGeneration then",
    "    ReleaseHeldInputs(ownerGeneration)",
    "    isPlaying = false",
    "    stopRequested = false",
    "    toggleTriggerArmed = false",
    "    playbackStartedAt = 0",
    "  end",
    "end",
    "",
    "function OnEvent(event, arg)",
    "  if event == \"PROFILE_ACTIVATED\" then",
    "    -- Required for button 1 because it is the primary mouse button.",
    "    EnablePrimaryMouseButtonEvents(true)",
    "    playbackGeneration = playbackGeneration + 1",
    "    isPlaying = false",
    "    stopRequested = true",
    "    ReleaseHeldInputs()",
    "    AbortMacro()",
    "    stopRequested = false",
    "    playbackStartedAt = 0",
    "    return",
    "  end",
    "  if event == \"MOUSE_BUTTON_PRESSED\" and arg == STOP_BUTTON then",
    "    RequestStop()",
    "    return",
    "  end",
    "  if arg ~= TRIGGER_BUTTON then return end",
    "  if TRIGGER_MODE == \"once\" and event == \"MOUSE_BUTTON_PRESSED\" then",
    "    PlayHarmonica()",
    "  elseif TRIGGER_MODE == \"hold\" then",
    "    if event == \"MOUSE_BUTTON_PRESSED\" then",
    "      PlayHarmonica()",
    "    elseif event == \"MOUSE_BUTTON_RELEASED\" then",
    "      RequestStop()",
    "    end",
    "  elseif TRIGGER_MODE == \"toggle\" and event == \"MOUSE_BUTTON_PRESSED\" then",
    "    if isPlaying then RequestStop() else PlayHarmonica() end",
    "  end",
    "end",
    ""
  );
  return lines.join("\n");
}

function razerKeyboardEvent(type, delay, makeCode) {
  return `    <MacroEvent><Type>${type}</Type><Delay>${delay}</Delay><Keyboard><KeyboardEvent><Type>${type}</Type><Makecode>${makeCode}</Makecode></KeyboardEvent></Keyboard></MacroEvent>`;
}

function razerMouseEvent(type, delay, button) {
  return `    <MacroEvent><Type>${type}</Type><Delay>${delay}</Delay><Mouse><MouseEvent><Type>${type}</Type><Button>${button}</Button></MouseEvent></Mouse></MacroEvent>`;
}

function generateRazerXml(sequence, version) {
  const events = [];
  sequence.notes.forEach((item) => {
    if (item.isRest) {
      events.push(`    <MacroEvent><Type>0</Type><Delay>${item.durationMs}</Delay></MacroEvent>`);
      return;
    }
    [...(item.modifier || "")].forEach((modifier) => events.push(razerMouseEvent(1, 0, MOUSE_BUTTONS[modifier].razer)));
    events.push(razerKeyboardEvent(1, 0, MAKE_CODES[item.key]));
    events.push(razerKeyboardEvent(2, item.pressMs, MAKE_CODES[item.key]));
    [...(item.modifier || "")].reverse().forEach((modifier) => events.push(razerMouseEvent(2, 0, MOUSE_BUTTONS[modifier].razer)));
    if (item.waitMs > 0) events.push(`    <MacroEvent><Type>0</Type><Delay>${item.waitMs}</Delay></MacroEvent>`);
  });
  const name = escapedXml(`${safeName()} · Synapse ${version}`);
  return `<?xml version="1.0" encoding="utf-8"?>\n<!-- Harmonica Deck experimental Synapse ${version} macro. Synapse 3 and 4 files are not interchangeable. -->\n<Macro xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n  <Name>${name}</Name>\n  <Guid>${makeUuid()}</Guid>\n  <MacroEvents>\n${events.join("\n")}\n  </MacroEvents>\n  <IsFolder>false</IsFolder>\n  <FolderGuid>00000000-0000-0000-0000-000000000000</FolderGuid>\n</Macro>\n`;
}

function download(content, filename, type) {
  const blob = new Blob([content], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 500);
}

const MACRO_DOWNLOAD_CONFIG = {
  "download-lua": {
    suffix: ".lua",
    type: "text/plain",
    requiresTriggerSettings: true,
    build: (sequence, triggerSettings) => generateLua(sequence, triggerSettings),
    success: "Lua 脚本已下载。"
  },
  "download-rz3": {
    suffix: "-synapse-3.xml",
    type: "application/xml",
    requiresTriggerSettings: false,
    build: (sequence) => generateRazerXml(sequence, 3),
    success: "Synapse 3 XML 已下载。"
  },
  "download-rz4": {
    suffix: "-synapse-4.xml",
    type: "application/xml",
    requiresTriggerSettings: false,
    build: (sequence) => generateRazerXml(sequence, 4),
    success: "Synapse 4 XML 已下载。"
  }
};

function clearMacroDownloadTimers() {
  window.clearInterval(macroDownloadTimer);
  window.clearTimeout(macroDownloadFinalizeTimer);
  macroDownloadTimer = null;
  macroDownloadFinalizeTimer = null;
}

function resetMacroDownloadProgress() {
  clearMacroDownloadTimers();
  elements.macroDownloadProgress.value = 0;
  elements.macroDownloadProgressLabel.textContent = "等待确认";
  elements.confirmMacroDownload.disabled = false;
}

function openMacroDownloadDialog(action) {
  const config = MACRO_DOWNLOAD_CONFIG[action];
  if (!config) return;
  const sequence = convert();
  if (!sequence) {
    toast("请先修正谱子错误。 ");
    return;
  }
  const triggerSettings = config.requiresTriggerSettings ? requireMacroTriggerSettings() : null;
  if (config.requiresTriggerSettings && !triggerSettings) return;
  const fileBase = safeName().replace(/\s+/g, "-").toLowerCase();
  pendingMacroDownload = {
    config,
    filename: `${fileBase || "delta-harmonica"}${config.suffix}`,
    sequence,
    triggerSettings
  };
  resetMacroDownloadProgress();
  elements.macroDownloadFilename.textContent = pendingMacroDownload.filename;
  if (typeof elements.macroDownloadDialog.showModal === "function") {
    elements.macroDownloadDialog.showModal();
    elements.confirmMacroDownload.focus();
    return;
  }
  startMacroDownload();
}

function startMacroDownload() {
  if (!pendingMacroDownload) return;
  const pending = pendingMacroDownload;
  clearMacroDownloadTimers();
  elements.confirmMacroDownload.disabled = true;
  let progress = 0;
  elements.macroDownloadProgress.value = progress;
  elements.macroDownloadProgressLabel.textContent = "正在生成文件 · 0%";
  macroDownloadTimer = window.setInterval(() => {
    progress = Math.min(100, progress + 10);
    elements.macroDownloadProgress.value = progress;
    elements.macroDownloadProgressLabel.textContent = progress < 100 ? `正在生成文件 · ${progress}%` : "文件已生成，准备下载…";
    if (progress < 100) return;
    clearMacroDownloadTimers();
    macroDownloadFinalizeTimer = window.setTimeout(() => {
      if (pendingMacroDownload !== pending) return;
      download(pending.config.build(pending.sequence, pending.triggerSettings), pending.filename, pending.config.type);
      if (elements.macroDownloadDialog.open) {
        elements.macroDownloadDialog.close();
      } else {
        pendingMacroDownload = null;
        resetMacroDownloadProgress();
      }
      toast(pending.config.success);
    }, 180);
  }, 70);
}

function compactText(value, field, limit) {
  const text = String(value ?? "").trim();
  if (!text) return { error: `请填写${field}。` };
  if (text.length > limit) return { error: `${field}不能超过 ${limit} 个字符。` };
  return { value: text };
}

function validateScoreMetadata(metadata) {
  const title = compactText(metadata.title, "歌名", 48);
  const artist = compactText(metadata.artist, "歌手/作者", 64);
  const sharedBy = compactText(metadata.sharedBy, "共享人", 48);
  if (title.error || artist.error || sharedBy.error) return { error: title.error || artist.error || sharedBy.error };
  const key = String(metadata.key ?? "").trim();
  if (!/^(?:1=)?[A-G](?:[#b♯♭])?$/i.test(key)) return { error: "调号格式应为 1=C、C、F♯ 或 A♭。" };
  const meter = String(metadata.meter ?? "").trim();
  const meterParts = meter.match(/^(\d{1,2})\/(\d{1,2})$/);
  if (!meterParts || Number(meterParts[1]) < 1 || ![1, 2, 4, 8, 16].includes(Number(meterParts[2]))) return { error: "拍号格式应为例如 4/4 或 6/8。" };
  const bpm = Number(metadata.bpm);
  if (!Number.isInteger(bpm) || bpm < 30 || bpm > 300) return { error: "BPM 必须是 30 到 300 之间的整数。" };
  return { value: { title: title.value, artist: artist.value, sharedBy: sharedBy.value, key, meter, bpm } };
}

function validateScorePackage(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return { error: "导入文件必须是 JSON 对象。" };
  if (![SONG_FILE_FORMAT, LEGACY_SONG_FILE_FORMAT].includes(payload.format)) return { error: "这不是 Delta Music 谱子文件。" };
  if (payload.version !== SONG_FILE_VERSION) return { error: `暂不支持谱子文件版本 ${payload.version ?? "未知"}。` };
  const metadata = validateScoreMetadata(payload);
  if (metadata.error) return metadata;
  const jianpu = String(payload.jianpu ?? "").trim();
  if (!jianpu) return { error: "导入文件缺少简谱内容。" };
  const sequence = parseJianpu(jianpu, metadata.value.bpm);
  if (sequence.error) return { error: `简谱无法载入：${sequence.error.message}` };
  return { value: { ...metadata.value, jianpu: sequenceToJianpu(sequence), source: "社区投稿" } };
}

function currentEditorMetadata(sharedBy = currentScoreCredit.sharedBy) {
  return validateScoreMetadata({
    title: elements.macroName.value,
    artist: elements.artistName.value,
    sharedBy,
    key: elements.keySignature.value,
    meter: elements.timeSignature.value,
    bpm: elements.bpm.value
  });
}

function openScoreExportDialog(mode = "download") {
  const sequence = convert();
  if (!sequence) { toast("请先修正谱子错误。 "); return; }
  const key = String(elements.keySignature.value).trim();
  const meter = String(elements.timeSignature.value).trim();
  if (!/^(?:1=)?[A-G](?:[#b♯♭])?$/i.test(key) || !/^\d{1,2}\/\d{1,2}$/.test(meter)) {
    toast("请先填写正确的调号与拍号。 ");
    return;
  }
  elements.exportSongTitle.value = elements.macroName.value.trim();
  elements.exportArtistName.value = elements.artistName.value.trim() || currentScoreCredit.artist;
  elements.exportSharedBy.value = currentScoreCredit.sharedBy;
  elements.exportMetaPreview.textContent = `${key} · ${meter} · ${elements.bpm.value} BPM · 简谱将自动标准化保存`;
  scoreExportMode = mode;
  const localLibrary = mode === "local-library";
  elements.scoreExportTitle.textContent = localLibrary ? "LOCAL_LIBRARY.EXE — MAINTAINER MODE" : "DELTA_MUSIC.EXE — SHARE YOUR SCORE";
  elements.scoreExportHeading.textContent = localLibrary ? "收录当前曲目" : "填写共享信息";
  elements.scoreExportDescription.innerHTML = localLibrary
    ? "将当前谱子写入本地工作区并重建社区曲库。不会自动提交或推送 GitHub。"
    : "导出为 <code>.deltamusic</code> 后可再次导入本工具。请加入 QQ 群 <b>1102489399</b>，把文件发给维护者审核入库。";
  elements.confirmScoreExportLabel.textContent = localLibrary ? "收录到本地曲库" : "下载 .deltamusic";
  elements.confirmScoreExportIcon.textContent = localLibrary ? "+" : "↓";
  elements.scoreExportDialog.showModal();
  elements.exportSongTitle.focus();
}

function scorePackageFromDialog() {
  const sequence = convert();
  if (!sequence) return { error: "请先修正谱子错误。" };
  const metadata = validateScoreMetadata({
    title: elements.exportSongTitle.value,
    artist: elements.exportArtistName.value,
    sharedBy: elements.exportSharedBy.value,
    key: elements.keySignature.value,
    meter: elements.timeSignature.value,
    bpm: elements.bpm.value
  });
  if (metadata.error) return metadata;
  return { value: {
    format: SONG_FILE_FORMAT,
    version: SONG_FILE_VERSION,
    ...metadata.value,
    jianpu: sequenceToJianpu(sequence)
  }};
}

function applyScorePackageMetadata(score) {
  elements.macroName.value = score.title;
  elements.artistName.value = score.artist;
  currentScoreCredit = { artist: score.artist, sharedBy: score.sharedBy };
}

function exportScorePackage() {
  const packaged = scorePackageFromDialog();
  if (packaged.error) { toast(packaged.error); return; }
  applyScorePackageMetadata(packaged.value);
  download(`${JSON.stringify(packaged.value, null, 2)}\n`, `${safeName().replace(/\s+/g, "-").toLowerCase() || "delta-music"}.deltamusic`, "application/json");
  elements.scoreExportDialog.close();
  toast(".deltamusic 文件已下载。加入 QQ 群 1102489399 分享给维护者吧。 ");
}

async function saveScoreToLocalLibrary() {
  const packaged = scorePackageFromDialog();
  if (packaged.error) { toast(packaged.error); return; }
  elements.confirmScoreExport.disabled = true;
  try {
    const response = await fetch("/api/local-library/songs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(packaged.value)
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "写入本地曲库失败。");
    if (!Array.isArray(result.songs)) throw new Error("本地服务返回的曲库数据无效。");
    applyScorePackageMetadata(packaged.value);
    SONG_LIBRARY.splice(0, SONG_LIBRARY.length, ...[...BUILTIN_SONG_LIBRARY, ...result.songs, ...PDMX_SONG_LIBRARY].map((song) => normalizeSong(song)));
    renderSongLibrary(elements.songSearch.value);
    elements.scoreExportDialog.close();
    toast(`《${packaged.value.title}》已${result.action === "updated" ? "更新" : "收录"}到本地工作区，待手动提交。`);
  } catch (error) {
    toast(error.message || "写入本地曲库失败。");
  } finally {
    elements.confirmScoreExport.disabled = false;
  }
}

async function enableLocalLibraryEntry() {
  try {
    const response = await fetch("/api/local-library/status", { headers: { Accept: "application/json" } });
    const status = await response.json();
    if (response.ok && status.localLibrary === true) elements.localLibraryButton.hidden = false;
  } catch {}
}

async function importScorePackage(file) {
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    const parsed = validateScorePackage(payload);
    if (parsed.error) throw new Error(parsed.error);
    loadSong(parsed.value);
    toast(`已导入《${parsed.value.title}》；可试听并继续编辑。`);
  } catch (error) {
    toast(error.message || "无法读取谱子文件。 ");
  } finally {
    elements.importScoreInput.value = "";
  }
}

async function importMidiFile(file, { refreshed = false } = {}) {
  if (!file) return false;
  try {
    openMidiTrackPicker(file, parseMidiData(await file.arrayBuffer()));
    lastMidiFile = file;
    if (refreshed) toast("已重新载入 MIDI；请确认音轨与片段。 ");
    completeTourAction("midi-file", "MIDI 已读取，请选择包含主旋律的音轨。");
    return true;
  } catch (error) {
    toast(error.message || "无法读取这个 MIDI 文件。 ");
    setTourStatus("无法读取该 MIDI 文件，请重新点击「导入 MIDI」选择有效文件。");
    return false;
  } finally {
    elements.importMidiInput.value = "";
  }
}

function applyMidiSelection() {
  if (!midiImportState) return;
  try {
    const selection = midiImportState;
    const converted = midiToSequence(selection.parsed, { trackIndex: selection.selectedTrackIndex, startTick: selection.startTick, endTick: selection.endTick });
    const smoothing = elements.midiSmoothing.checked ? smoothMidiSequence(converted.sequence, converted.bpm) : { sequence: converted.sequence, connectedGaps: 0 };
    converted.sequence = smoothing.sequence;
    stopPreview();
    finishRecording({ apply: false });
    elements.macroName.value = selection.title;
    elements.artistName.value = "";
    elements.keySignature.value = converted.key;
    elements.timeSignature.value = converted.meter;
    elements.bpm.value = converted.bpm;
    currentScoreCredit = { artist: "", sharedBy: "" };
    converted.sequence.notes.forEach((item, index) => { item.index = index; });
    syncSequenceToEditors(converted.sequence);
    [elements.jianpuScore, elements.score, elements.recordedScore, elements.keyboardScore].forEach((editor) => { editor.scrollTop = 0; });
    elements.jianpuLineNumbers.scrollTop = 0;
    elements.lineNumbers.scrollTop = 0;
    elements.keyboardLineNumbers.scrollTop = 0;
    setInputMode("jianpu", { force: true, silent: true });
    elements.jianpuScore.focus();
    const transposeMessage = converted.transpose ? ` · 已移调 ${converted.transpose > 0 ? "+" : ""}${converted.transpose} 半音以适配口琴音域` : "";
    const tempoWarning = converted.hasTempoChanges ? " · 原文件含变速，已采用起始 BPM" : "";
    const chordMessage = converted.collapsedChordNotes ? ` · 和弦已取最高音（合并 ${converted.collapsedChordNotes} 个和声音）` : "";
    const ignoredEventMessage = describeIgnoredMidiEvents(converted.ignoredInvalidNonNoteEvents);
    const smoothingMessage = elements.midiSmoothing.checked ? ` · 流畅演奏已连接 ${smoothing.connectedGaps} 处短断音` : " · 保留原始 MIDI 断音";
    setValidation(`MIDI 转换完成 · 已选音轨 ${String(selection.selectedTrackIndex + 1).padStart(2, "0")} · 截取 ${midiTickToTime(selection.parsed, selection.endTick - selection.startTick)} · ${converted.selectedNotes} 个旋律音符${chordMessage}${ignoredEventMessage}${smoothingMessage}${transposeMessage}${tempoWarning}。`, "success");
    toast(`已将《${selection.title}》选定片段转换为可编辑简谱。`);
  } catch (error) {
    toast(error.message || "无法转换所选 MIDI 片段。 ");
  }
}

let toastTimer;
function toast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => elements.toast.classList.remove("show"), 2400);
}

async function copyLua(sequence) {
  const triggerSettings = requireMacroTriggerSettings();
  if (!triggerSettings) return;
  const lua = generateLua(sequence, triggerSettings);
  try {
    await navigator.clipboard.writeText(lua);
    toast("Lua 已复制到剪贴板。");
  } catch {
    toast("浏览器未授权剪贴板；请使用下载功能。 ");
  }
}

[elements.score, elements.jianpuScore, elements.recordedScore, elements.keyboardScore].forEach((textarea) => textarea.addEventListener("input", () => { lastMidiFile = null; resetMidiTrackPicker(); stopPreview(); updateLineNumbers(); convert(); }));
editorLineNumberPairs.forEach(([textarea, gutter]) => textarea.addEventListener("scroll", () => syncLineNumbers(textarea, gutter)));
elements.bpm.addEventListener("input", handleBpmChange);
elements.convertButton.addEventListener("click", playPreview);
elements.importMidiButton.addEventListener("click", () => {
  if (activeTour?.steps[activeTour.stepIndex]?.action === "midi-file") setTourStatus("系统文件选择器已打开；请选择 MIDI 文件。若取消，可再次点击导入。");
  elements.importMidiInput.click();
});
elements.importMidiInput.addEventListener("change", () => importMidiFile(elements.importMidiInput.files?.[0]));
elements.midiSmoothing.addEventListener("change", () => {
  if (midiImportState?.applied) applyMidiSelection();
  else if (midiImportState) toast("流畅演奏设置将在确认选定音轨与片段时生效。 ");
  else toast("流畅演奏设置将在下次导入 MIDI 时生效。 ");
});
elements.midiTrackList.addEventListener("click", (event) => {
  const track = event.target.closest("[data-midi-track-index]");
  if (!track || !midiImportState) return;
  midiImportState.selectedTrackIndex = Number(track.dataset.midiTrackIndex);
  Object.assign(midiImportState, midiTrackBounds(midiImportState.parsed, midiImportState.selectedTrackIndex, midiImportState.durationTicks));
  midiImportState.rangeAutoTrimmed = true;
  midiImportState.applied = false;
  renderMidiTrackPicker();
});
[elements.midiRangeStartInput, elements.midiRangeEndInput].forEach((input) => input.addEventListener("input", () => {
  if (midiImportState) {
    midiImportState.applied = false;
    midiImportState.rangeAutoTrimmed = false;
  }
  updateMidiRangeUi();
}));
elements.confirmMidiSelection.addEventListener("click", () => {
  if (!midiImportState) return;
  midiImportState.applied = true;
  applyMidiSelection();
  completeTourAction("midi-confirm", "谱子已生成，接下来前往宏导出。");
});
elements.importScoreButton.addEventListener("click", () => elements.importScoreInput.click());
elements.importScoreInput.addEventListener("change", () => importScorePackage(elements.importScoreInput.files?.[0]));
elements.macroExportButton.addEventListener("click", () => {
  elements.macroExportSection.scrollIntoView({ behavior: "smooth", block: "start" });
  completeTourAction("macro-export", "已进入导出区。");
});
elements.exportScoreButton.addEventListener("click", openScoreExportDialog);
elements.confirmScoreExport.addEventListener("click", () => {
  if (scoreExportMode === "local-library") saveScoreToLocalLibrary();
  else exportScorePackage();
});
elements.clearButton.addEventListener("click", () => {
  finishRecording({ apply: false });
  stopPreview();
  lastMidiFile = null;
  resetMidiTrackPicker();
  const activeEditor = inputMode === "jianpu" ? elements.jianpuScore : inputMode === "record" ? elements.recordedScore : inputMode === "keyboard" ? elements.keyboardScore : elements.score;
  [elements.jianpuScore, elements.recordedScore, elements.score, elements.keyboardScore].forEach((editor) => { editor.value = ""; });
  updateLineNumbers();
  convert();
  activeEditor.focus();
});
elements.recordToggle.addEventListener("click", () => { if (recording) finishRecording(); else beginRecording(); });
elements.modifierChoices.forEach((button) => button.addEventListener("click", () => {
  selectedRecordModifier = button.dataset.recordModifier;
  elements.modifierChoices.forEach((choice) => choice.classList.toggle("active", choice === button));
}));
elements.recordKeyboard.addEventListener("pointerdown", (event) => {
  const key = event.target.closest("[data-record-note]");
  if (!key || event.button !== 0) return;
  event.preventDefault();
  try { key.setPointerCapture(event.pointerId); } catch {}
  startRecordingNote(key.dataset.recordNote, `pointer:${event.pointerId}`);
});
elements.recordKeyboard.addEventListener("pointerup", (event) => {
  endRecordingNote(`pointer:${event.pointerId}`);
});
elements.recordKeyboard.addEventListener("pointercancel", (event) => {
  endRecordingNote(`pointer:${event.pointerId}`);
});
window.addEventListener("keydown", (event) => {
  if (!recording || event.repeat) return;
  const note = KEY_TO_NOTE[event.key.toLowerCase()];
  if (!note) return;
  event.preventDefault();
  startRecordingNote(note, `keyboard:${event.code}`);
});
window.addEventListener("keyup", (event) => {
  if (!recording) return;
  const note = KEY_TO_NOTE[event.key.toLowerCase()];
  if (!note) return;
  event.preventDefault();
  endRecordingNote(`keyboard:${event.code}`);
});
window.addEventListener("blur", () => finishActiveRecordPress());
elements.previewButton.addEventListener("click", togglePreview);
elements.previewButton.addEventListener("pointerdown", prewarmAudioEngine, { passive: true });
elements.restartButton.addEventListener("click", () => playPreview(0));
elements.stopButton.addEventListener("click", stopPreview);
elements.previewProgress.addEventListener("input", () => {
  const position = Number(elements.previewProgress.value);
  setPreviewProgress(position);
  highlightTimelinePosition(position);
});
elements.previewProgress.addEventListener("change", () => playPreview(Number(elements.previewProgress.value)));
elements.timeline.addEventListener("click", (event) => {
  const row = event.target.closest("[data-time-ms]");
  if (row) playPreview(Number(row.dataset.timeMs));
});
elements.timeline.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("[data-time-ms]");
  if (!row) return;
  event.preventDefault();
  playPreview(Number(row.dataset.timeMs));
});
elements.volume.addEventListener("input", () => {
  if (audioContext && masterGain) masterGain.gain.setTargetAtTime(Number(elements.volume.value) / 100, audioContext.currentTime, 0.01);
});
elements.macroTriggerButton.addEventListener("input", clearMacroTriggerValidation);
elements.macroStopButton.addEventListener("input", clearMacroTriggerValidation);
elements.macroTriggerMode.addEventListener("change", () => {
  updateMacroTriggerHint();
  clearMacroTriggerValidation();
});
elements.confirmMacroDownload.addEventListener("click", startMacroDownload);
elements.macroDownloadDialog.addEventListener("close", () => {
  clearMacroDownloadTimers();
  pendingMacroDownload = null;
  elements.confirmMacroDownload.disabled = false;
  elements.macroDownloadProgress.value = 0;
  elements.macroDownloadProgressLabel.textContent = "等待确认";
});
elements.exportButtons.forEach((button) => button.addEventListener("click", async () => {
  const sequence = convert();
  if (!sequence) { toast("请先修正谱子错误。 "); return; }
  const action = button.dataset.action;
  if (action === "copy-lua") await copyLua(sequence);
  if (["download-lua", "download-rz3", "download-rz4"].includes(action)) openMacroDownloadDialog(action);
}));
elements.guideButtons.forEach((button) => button.addEventListener("click", () => openSectionGuide(button.dataset.guide)));
elements.inputModeButtons.forEach((button) => button.addEventListener("click", () => setInputMode(button.dataset.inputMode)));
elements.directoryButtons.forEach((button) => button.addEventListener("click", () => {
  const action = button.dataset.directoryAction;
  if (action === "library") {
    document.querySelector(".library-deck")?.scrollIntoView({ behavior: "smooth", block: "start" });
    elements.songSearch.focus({ preventScroll: true });
  }
  if (action === "midi") elements.importMidiInput.click();
  if (action === "manual" && setInputMode("jianpu")) {
    elements.editorPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    elements.jianpuScore.focus({ preventScroll: true });
  }
}));
elements.tourStartButtons.forEach((button) => button.addEventListener("click", () => startTour(button.dataset.tourStart, button)));
elements.tourPrevious.addEventListener("click", () => moveTour(-1));
elements.tourNext.addEventListener("click", () => {
  if (!activeTour) return;
  if (activeTour.steps[activeTour.stepIndex].terminal) endTour();
  else moveTour(1);
});
elements.tourSkip.addEventListener("click", endTour);
elements.tourClose.addEventListener("click", endTour);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activeTour) {
    event.preventDefault();
    endTour();
  }
});
elements.songSearch.addEventListener("input", () => renderSongLibrary(elements.songSearch.value));
elements.songGrid.addEventListener("click", (event) => {
  const actionButton = event.target.closest("[data-song-action]");
  const card = actionButton?.closest("[data-song-index]");
  if (!actionButton || !card) return;
  const destination = actionButton.dataset.songAction === "export" ? "export" : "editor";
  loadSong(SONG_LIBRARY[Number(card.dataset.songIndex)], { destination });
  if (destination === "export") completeTourAction("library-export", "曲目已载入，正在打开导出区。");
});
elements.manualMacroButton.addEventListener("click", openKeyboardMacroDialog);
function openUploadHelpDialog(status = "") {
  elements.uploadCopyStatus.textContent = status;
  elements.uploadCopyStatus.hidden = !status;
  if (typeof elements.uploadHelpDialog.showModal === "function") {
    elements.uploadHelpDialog.showModal();
    return;
  }
  toast(status || "请加入 QQ 群 1102489399 上传谱子。 ");
}

elements.qqGroupButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText("1102489399");
    openUploadHelpDialog("群号已复制");
  } catch {
    openUploadHelpDialog("复制失败，请手动复制群号 1102489399");
  }
});
elements.uploadScoreButton.addEventListener("click", () => {
  openUploadHelpDialog();
});
elements.localLibraryButton.addEventListener("click", () => openScoreExportDialog("local-library"));

renderSongLibrary();
enableLocalLibraryEntry();
updateMacroTriggerHint();
updateLineNumbers();
setInputMode("jianpu", { force: true, silent: true });
if (SONG_LIBRARY[0]) loadSong(SONG_LIBRARY[0]);
window.addEventListener("resize", () => {
  scheduleWorkbenchHeightSync();
  updateTourPosition();
});
window.addEventListener("scroll", updateTourPosition, { passive: true });
document.addEventListener("scroll", updateTourPosition, { capture: true, passive: true });
if (typeof ResizeObserver === "function") {
  new ResizeObserver(scheduleWorkbenchHeightSync).observe(elements.editorPanel);
}
if (typeof MutationObserver === "function") {
  new MutationObserver(scheduleWorkbenchHeightSync).observe(elements.editorPanel, { attributes: true, childList: true, subtree: true });
}
scheduleWorkbenchHeightSync();
