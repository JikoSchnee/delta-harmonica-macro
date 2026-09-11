const NOTE_KEYS = { "1": "z", "2": "x", "3": "c", "4": "v", "5": "b", "6": "n", "7": "m", "1'": "," };
const MAKE_CODES = { z: 44, x: 45, c: 46, v: 47, b: 48, n: 49, m: 50, ",": 51 };
const MOUSE_BUTTONS = { L: { name: "左键降调", ghub: 1, razer: 1 }, M: { name: "中键半音", ghub: 3, razer: 3 }, R: { name: "右键升调", ghub: 2, razer: 2 } };
const PREVIEW_MIDI = { "1": 60, "2": 62, "3": 64, "4": 65, "5": 67, "6": 69, "7": 71, "1'": 72 };
const PREVIEW_OFFSETS = { L: -12, M: 1, R: 12 };
const KEY_TO_NOTE = { z: "1", x: "2", c: "3", v: "4", b: "5", n: "6", m: "7", ",": "1'" };
const RECORD_BEATS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
const DIATONIC_MIDI = { "1": 60, "2": 62, "3": 64, "4": 65, "5": 67, "6": 69, "7": 71 };
const BUILTIN_SONG_LIBRARY = [
 { title: "鸟之诗", detail: "1=D · 4/4 · 120 BPM · 双页图片识谱版", bpm: 120, jianpu: `(0 5'_ 6'_ 1'_ | 7' - 0 5'_ 6'_ 1'_ | 2' - 0 5'_ 6'_ 1'_ | 5' - - 0 4' | 3' - 0 5'_ 6'_ 1'_ |
7' - 0 5'_ 6'_ 1'_ | 2' - 0 3'_ 5'_ 7'_ | 6' - - -) |
0 0_ ,6_ ,7_ 1_ 5 | 3 3_ 2_ 3_ 3 - |
0 2_ 3_ 5_ 3_ 5_ 1_ | ,7_. ,6_~ ,6_ ,3_~ ,3 0_ 2_ | 3 5 6 7 | 3 3_ 2_ 3_ 3 - |
0 2_ 3_ 5_ 1_ ,7_ ,1_ | ,7_ ,7_ ,6_ ,3_ ,3 - | 0 0_ ,6_ ,7_ 1_ 5 | 3 3_ 2_ 3_ 3 - |
0 2_ 3_ 5_ 3_ 5_ 1_ | 7 - - 7 6 | 6 - 0 6 | 7 - - 7 6 | 6 - - - |
||: 0 0_ 6_ 6_. 6_ 6_ 6_ | 6_. 5_~ 5_~ 5_~ 5_ 6 7 | 1'. 7_~ 7_ 6_~ 6_ 3_ 3_ | 3 3 2_ 1_ 1_ |
0 0_ 6_ 6_. 6_ 6_ 6_ | 6_. 5_~ 5_~ 5_~ 5_ 3 5 | 6_. 7_~ 7_ 1'~ 1' - | 1' 0 0 0 |
0 0_ 6_ 6_. 6_ 6_ 6_ | 6_. 5_~ 5_~ 5_~ 5_ 6 7 | 1'. 7_~ 7_ 6_~ 6_ 3_ 3_ | 3 - 2_ 1_ 1_ |
0 0_ 3_ 3_ 3_ 3_ 3_ | 2_. 3_ 3_ 5_ 3_ 3_ 5 | 6 - 1' 7 6 | 6 - 0 4 3 |
3_ 3_ 3_ 2_ 3_ 3 - | 0 3 4 5 | 2_. 7_ 7_ - | 0 0_ 7_ 1' 2 0 |
3_ 3_ 3_ 6_ 3_ 3 - | 3 - 0 2 1 | 2 2 1 2 5 | 5 - - 0 |
3_ 3_ 3_ 2_ 3_ 3 - | 0 3 4 5 | 2_. 7_ 7_ - | 0 0_ 7_ 1' 2 0 |
3_ 3_ 3_ 2_ 3_ 3 - | 3 - 0 2 1 | 2 2 1 2 3 3 | 3 0 0_ 6_ 7_ 1_ 5 |
3 3_ 2_ 3_ 3 - | 0 2_ 3_ 5_ 1_ ,7_ ,1_ | ,7_ ,7_ ,6_ ,3_ ,3 - | 0 0_ ,6_ ,7_ 1_ 5 |
3 3_ 2_ 3_ 3 - | 0 2_ 3_ 5_ 3_ 5_ 1_ | ,7_. ,6_~ ,6_ ,3_~ ,3 0_ 2_ | 3 5 6 7 |
3 3_ 2_ 3_ 3 - | 0 2_ 3_ 5_ 1_ ,7_ ,1_ | ,7_ ,7_ ,6_ ,3_ ,3 - | 0 0_ ,6_ ,7_ 1_ 5 |
3 3_ 2_ 3_ 3 - | 0 2_ 3_ 5_ 3_ 5_ 1_ | 7 - - 7 6 | 6 - 0 6 |
7 - - 7 6 | 6 - - - | (6' 1' ,7 1' 2' | 0 1' 0 7' 0 6' 5' 2' | 2'. 3' 6' 0 |
6' 7'_ 6'_ 7'_ 1' 2' 1' | 1' 7' 2' 7' 1' 2' | 1' 7' 2' 0 4' 3' 1' | 6' 7' 6' - 0 5' | 6 - - -) :||
6' 0 0_ ,6_ ,7_ 1_ 5 || 7 - - - | 1' - - - | (6' 1' ,7 1' 2' | 0 1' 0 7' 0 6' 5' 2' |
2' - 0 5' 0 6' | 0 7'_ 6'_ 7'_ 1' 2' 1' 7' | 1'. 2' 7' 1' 2' | 0 1' 0 7' 0 6' 5' 2' |
3 - 0 3 4 3 | 6 7 1' 2' 0 1' 7 | 6 1' 7 1' 2' | 0 1' 0 7' 0 6' 5' 2' |
2_. 3' 6_. 5 | 6 7_ 6_ 7_ 1' 2' 1' | 1' 7 1' 2' 7 1' 2' | 0 7' 0 3' 0 4 3 |
6 7 6 - 0 5 | 6 - - - ||: 6 - - 6 5 | 6 - - - ||: 1' 7 6 2 1 0 |
1' 7 6 2 1 0 | 1' 7 6 2 1 0 | 1' 7 6 2 1 0 | 1' 7 6 2 1 0 :|| 0 0) ||` },
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
const SONG_FILE_FORMAT = "harmonica-deck-score";
const SONG_FILE_VERSION = 1;
const SONG_LIBRARY = [...BUILTIN_SONG_LIBRARY, ...PDMX_SONG_LIBRARY, ...COMMUNITY_SONG_LIBRARY].map((song) => normalizeSong(song));

const elements = {
  score: document.querySelector("#score"), jianpuScore: document.querySelector("#jianpuScore"), recordedScore: document.querySelector("#recordedScore"), bpm: document.querySelector("#bpm"), macroName: document.querySelector("#macroName"), artistName: document.querySelector("#artistName"), keySignature: document.querySelector("#keySignature"), timeSignature: document.querySelector("#timeSignature"), trigger: document.querySelector("#triggerButton"),
  workbench: document.querySelector(".workbench"), editorPanel: document.querySelector(".editor-panel"),
  convertButton: document.querySelector("#convertButton"), clearButton: document.querySelector("#clearButton"), importScoreButton: document.querySelector("#importScoreButton"), macroExportButton: document.querySelector("#macroExportButton"), macroExportSection: document.querySelector("#macro-export"), exportScoreButton: document.querySelector("#exportScoreButton"), importScoreInput: document.querySelector("#importScoreInput"),
  lineNumbers: document.querySelector("#lineNumbers"), jianpuLineNumbers: document.querySelector("#jianpuLineNumbers"), validation: document.querySelector("#validation"), status: document.querySelector("#parseStatus"),
  totalTime: document.querySelector("#totalTime"), noteCount: document.querySelector("#noteCount"), eventCount: document.querySelector("#eventCount"), beatMs: document.querySelector("#beatMs"),
  timeline: document.querySelector("#timeline"), monitorDot: document.querySelector(".monitor-dot"), toast: document.querySelector("#toast"), exportButtons: [...document.querySelectorAll("[data-action]")],
  previewButton: document.querySelector("#previewButton"), restartButton: document.querySelector("#restartButton"), stopButton: document.querySelector("#stopButton"), volume: document.querySelector("#volume"), previewState: document.querySelector("#previewState"),
  inputModeButtons: [...document.querySelectorAll("[data-input-mode]")], inputPanes: [...document.querySelectorAll("[data-input-pane]")], songGrid: document.querySelector("#songGrid"), songSearch: document.querySelector("#songSearch"), libraryCount: document.querySelector("#libraryCount"), uploadScoreButton: document.querySelector("#uploadScoreButton"), uploadHelpDialog: document.querySelector("#uploadHelpDialog"), uploadCopyStatus: document.querySelector("#uploadCopyStatus"),
  recordToggle: document.querySelector("#recordToggle"), recordState: document.querySelector("#recordState"), recordCount: document.querySelector("#recordCount"), recordKeyboard: document.querySelector("#recordKeyboard"), modifierChoices: [...document.querySelectorAll("[data-record-modifier]")],
  qqGroupButton: document.querySelector("#qqGroupButton"), macroDownloadDialog: document.querySelector("#macroDownloadDialog"), macroDownloadFilename: document.querySelector("#macroDownloadFilename"), macroDownloadProgress: document.querySelector("#macroDownloadProgress"), macroDownloadProgressLabel: document.querySelector("#macroDownloadProgressLabel"), confirmMacroDownload: document.querySelector("#confirmMacroDownload"), scoreExportDialog: document.querySelector("#scoreExportDialog"), exportSongTitle: document.querySelector("#exportSongTitle"), exportArtistName: document.querySelector("#exportArtistName"), exportSharedBy: document.querySelector("#exportSharedBy"), exportMetaPreview: document.querySelector("#exportMetaPreview"), confirmScoreExport: document.querySelector("#confirmScoreExport")
};

let currentSequence = null;
let audioContext = null;
let masterGain = null;
let activePreview = null;
let workbenchHeightSyncFrame = 0;
let pendingMacroDownload = null;
let macroDownloadTimer = null;
let macroDownloadFinalizeTimer = null;
let inputMode = "jianpu";

function syncWorkbenchHeight() {
  if (!elements.workbench || !elements.editorPanel) return;
  if (window.matchMedia("(max-width: 860px)").matches) {
    elements.workbench.style.removeProperty("--workbench-max-height");
    return;
  }
  const editorHeight = Math.ceil(elements.editorPanel.scrollHeight);
  if (editorHeight > 0) elements.workbench.style.setProperty("--workbench-max-height", `${editorHeight}px`);
}

function scheduleWorkbenchHeightSync() {
  window.cancelAnimationFrame(workbenchHeightSyncFrame);
  workbenchHeightSyncFrame = window.requestAnimationFrame(syncWorkbenchHeight);
}
let recording = null;
let selectedRecordModifier = "";
let liveRecordingVoice = null;
let currentScoreCredit = { artist: "", sharedBy: "" };

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
  return { notes: enriched, beatMs: Math.round(beatMs), totalMs: cursor, events: enriched.reduce((sum, item) => sum + item.eventCount, 0) };
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

function formatTime(milliseconds) {
  const ms = Math.max(0, Math.round(milliseconds));
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
}

const editorLineNumberPairs = [
  [elements.score, elements.lineNumbers],
  [elements.jianpuScore, elements.jianpuLineNumbers]
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
    <button class="song-card" data-song-index="${song.index}" data-index="${String(song.index + 1).padStart(2, "0")}" type="button">
      <span class="song-number">TRACK ${String(song.index + 1).padStart(2, "0")}</span>
      <h3>${escapeHtml(song.title)}</h3>
      <p class="song-artist">${escapeHtml(song.artist)}</p>
      <div class="song-meta"><span>${escapeHtml(song.key)}</span><span>${escapeHtml(song.meter)}</span><span>${escapeHtml(song.bpm)} BPM</span></div>
      <span class="song-share">共享：${escapeHtml(song.sharedBy)}</span>
    </button>
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

function syncSequenceToEditors(sequence, { except = null } = {}) {
  if (except !== "jianpu") elements.jianpuScore.value = sequenceToJianpu(sequence);
  const precise = sequenceToPrecise(sequence);
  if (except !== "precise") elements.score.value = precise;
  if (except !== "record") elements.recordedScore.value = precise;
  updateLineNumbers();
}

function loadSong(song) {
  stopPreview();
  finishRecording({ apply: false });
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
  [elements.jianpuScore, elements.score, elements.recordedScore].forEach((editor) => { editor.scrollTop = 0; });
  elements.jianpuLineNumbers.scrollTop = 0;
  elements.lineNumbers.scrollTop = 0;
  setInputMode("jianpu", { force: true, silent: true });
  elements.jianpuScore.focus();
  syncLineNumbers(elements.jianpuScore, elements.jianpuLineNumbers);
  document.querySelector(".workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
  toast(`已载入《${song.title}》· ${song.bpm} BPM。`);
}

const MODE_LABELS = { jianpu: "简谱模式", record: "录制模式", precise: "精确模式" };

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
  return Number.isInteger(value) ? String(value) : String(value).replace(/0+$/, "").replace(/\.$/, "");
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

function updateMonitor(sequence) {
  if (!sequence) {
    elements.totalTime.textContent = "--:--.---";
    elements.noteCount.textContent = "--";
    elements.eventCount.textContent = "--";
    elements.beatMs.textContent = "-- MS / BEAT";
    elements.timeline.innerHTML = '<li class="empty-state">转换后将在这里显示每个音符的按键时刻。</li>';
    elements.monitorDot.classList.remove("active");
    return;
  }
  elements.totalTime.textContent = formatTime(sequence.totalMs);
  elements.noteCount.textContent = sequence.notes.length;
  elements.eventCount.textContent = sequence.events;
  elements.beatMs.textContent = `${sequence.beatMs} MS / BEAT`;
  elements.monitorDot.classList.add("active");
  elements.timeline.innerHTML = sequence.notes.map((item) => {
    const modifier = item.modifier ? `${item.modifier} + ` : "";
    const detail = item.isRest ? `休止 ${item.durationMs}ms` : `${modifier}${item.key.toUpperCase()} · 按住 ${item.pressMs}ms · 紧接下一音`;
    return `<li data-note-index="${item.index ?? 0}"><span class="time">${formatTime(item.timeMs)}</span><span class="timeline-key${item.isRest ? " rest" : item.modifier ? " modifier" : ""}">${item.isRest ? "休" : item.note}</span><span class="event-detail">${detail}</span></li>`;
  }).join("");
}

function convert() {
  updateLineNumbers();
  const bpm = Number(elements.bpm.value);
  const sequence = inputMode === "jianpu" ? parseJianpu(elements.jianpuScore.value, bpm) : parseScore(inputMode === "record" ? elements.recordedScore.value : elements.score.value, bpm);
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
  const offset = [...(item.modifier || "")].reduce((sum, modifier) => sum + PREVIEW_OFFSETS[modifier], 0);
  const midi = PREVIEW_MIDI[item.note] + offset;
  return 440 * (2 ** ((midi - 69) / 12));
}

function createHarmonicaVoice(context, startAt, duration, frequency) {
  const gain = context.createGain();
  const filter = context.createBiquadFilter();
  const oscillator = context.createOscillator();
  const shimmer = context.createOscillator();
  const shimmerGain = context.createGain();
  const hasScheduledEnd = Number.isFinite(duration) && duration > 0;
  const endAt = hasScheduledEnd ? startAt + duration : null;

  oscillator.type = "sawtooth";
  oscillator.frequency.setValueAtTime(frequency, startAt);
  shimmer.type = "sine";
  shimmer.frequency.setValueAtTime(frequency * 2.01, startAt);
  shimmerGain.gain.value = 0.085;
  filter.type = "lowpass";
  filter.frequency.setValueAtTime(Math.min(4100, frequency * 14), startAt);
  filter.Q.value = 1.6;

  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(0.16, startAt + 0.018);
  gain.gain.exponentialRampToValueAtTime(0.1, hasScheduledEnd ? Math.min(endAt - 0.018, startAt + 0.11) : startAt + 0.11);
  if (hasScheduledEnd) gain.gain.exponentialRampToValueAtTime(0.0001, endAt);
  oscillator.connect(filter).connect(gain).connect(masterGain);
  shimmer.connect(shimmerGain).connect(filter);
  oscillator.start(startAt);
  shimmer.start(startAt);
  if (hasScheduledEnd) {
    oscillator.stop(endAt + 0.02);
    shimmer.stop(endAt + 0.02);
  }
  return { context, gain, nodes: [oscillator, shimmer] };
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

function stopPreview() {
  if (!activePreview) return;
  activePreview.nodes.forEach((node) => { try { node.stop(); } catch {} });
  clearPreviewTimers(activePreview);
  activePreview = null;
  clearTimelinePlayback();
  setPreviewUi("ready");
}

function previewPositionMs(preview) {
  const position = (preview.context.currentTime - preview.startAt) * 1000;
  return Math.max(0, Math.min(preview.sequence.totalMs, position));
}

function schedulePreviewTimers(preview, positionMs, isInitial = false) {
  clearPreviewTimers(preview);
  const leadMs = isInitial ? 45 : 0;
  preview.sequence.notes.forEach((item, index) => {
    const remainingMs = item.timeMs - positionMs;
    if (remainingMs < -1) return;
    preview.timers.push(window.setTimeout(() => {
      clearTimelinePlayback();
      const row = elements.timeline.querySelector(`[data-note-index="${index}"]`);
      row?.classList.add("playing");
      keepTimelineRowVisible(row);
    }, Math.max(0, remainingMs + leadMs)));
  });
  preview.timers.push(window.setTimeout(() => stopPreview(), Math.max(0, preview.sequence.totalMs - positionMs) + 110));
}

async function pausePreview() {
  if (!activePreview || activePreview.state !== "playing") return;
  const preview = activePreview;
  clearPreviewTimers(preview);
  try {
    await preview.context.suspend();
    preview.positionMs = previewPositionMs(preview);
    preview.state = "paused";
    setPreviewUi("paused");
  } catch (error) {
    schedulePreviewTimers(preview, previewPositionMs(preview));
    toast(error.message || "无法暂停试听。 ");
  }
}

async function resumePreview() {
  if (!activePreview || activePreview.state !== "paused") return;
  const preview = activePreview;
  try {
    await preview.context.resume();
    preview.startAt = preview.context.currentTime - preview.positionMs / 1000;
    preview.state = "playing";
    schedulePreviewTimers(preview, preview.positionMs);
    setPreviewUi("playing");
  } catch (error) {
    toast(error.message || "无法继续试听。 ");
  }
}

function togglePreview() {
  if (!activePreview) return playPreview();
  if (activePreview.state === "playing") return pausePreview();
  return resumePreview();
}

async function playPreview() {
  if (recording) { toast("请先完成录制，再播放谱子。 "); return; }
  const sequence = convert();
  if (!sequence) { toast("请先修正谱子错误。 "); return; }
  stopPreview();
  try {
    const context = await wakeAudioEngine();
    masterGain.gain.setTargetAtTime(Number(elements.volume.value) / 100, context.currentTime, 0.01);
    const nodes = [];
    const timers = [];
    const startAt = context.currentTime + 0.045;
    sequence.notes.forEach((item, index) => {
      const noteLength = Math.max(0.055, item.durationMs / 1000 + 0.028);
      if (!item.isRest) nodes.push(...scheduleHarmonicaTone(context, startAt + item.timeMs / 1000, noteLength, previewFrequency(item)));
    });
    activePreview = { context, nodes, timers, sequence, startAt, positionMs: 0, state: "playing" };
    schedulePreviewTimers(activePreview, 0, true);
    setPreviewUi("playing");
  } catch (error) {
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

function generateLua(sequence) {
  const triggerValue = Number(elements.trigger.value);
  const trigger = Number.isInteger(triggerValue) && triggerValue > 0 ? triggerValue : 0;
  const lines = [
    "-- Harmonica Deck · Delta Force harmonica sequence",
    `-- Score: ${safeName()} | ${sequence.notes.length} notes | ${elements.bpm.value} BPM`,
    "-- Set TRIGGER_BUTTON to your mouse button code before use (0 disables playback).",
    "-- Each key is held for its full score duration, then released immediately before the next note.",
    `local TRIGGER_BUTTON = ${trigger}`,
    "",
    "function PlayHarmonica()"
  ];
  sequence.notes.forEach((item, index) => {
    lines.push(`  -- ${String(index + 1).padStart(2, "0")}: ${item.modifier ? `${item.modifier}+` : ""}${item.note}, ${item.beats} beat(s)`);
    if (item.isRest) {
      lines.push(`  Sleep(${item.durationMs})`);
      return;
    }
    [...(item.modifier || "")].forEach((modifier) => lines.push(`  PressMouseButton(${MOUSE_BUTTONS[modifier].ghub})`));
    lines.push(`  PressKey(\"${item.key}\")`);
    lines.push(`  Sleep(${item.pressMs})`);
    lines.push(`  ReleaseKey(\"${item.key}\")`);
    [...(item.modifier || "")].reverse().forEach((modifier) => lines.push(`  ReleaseMouseButton(${MOUSE_BUTTONS[modifier].ghub})`));
    if (item.waitMs > 0) lines.push(`  Sleep(${item.waitMs})`);
  });
  lines.push("end", "", "function OnEvent(event, arg)", "  if event == \"MOUSE_BUTTON_PRESSED\" and arg == TRIGGER_BUTTON then", "    PlayHarmonica()", "  end", "end", "");
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
    build: (sequence) => generateLua(sequence),
    success: "Lua 脚本已下载。"
  },
  "download-rz3": {
    suffix: "-synapse-3.xml",
    type: "application/xml",
    build: (sequence) => generateRazerXml(sequence, 3),
    success: "Synapse 3 XML 已下载。"
  },
  "download-rz4": {
    suffix: "-synapse-4.xml",
    type: "application/xml",
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
  const fileBase = safeName().replace(/\s+/g, "-").toLowerCase();
  pendingMacroDownload = {
    config,
    filename: `${fileBase || "delta-harmonica"}${config.suffix}`,
    sequence
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
      download(pending.config.build(pending.sequence), pending.filename, pending.config.type);
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
  if (payload.format !== SONG_FILE_FORMAT) return { error: "这不是 Harmonica Deck 谱子文件。" };
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

function openScoreExportDialog() {
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
  elements.scoreExportDialog.showModal();
  elements.exportSongTitle.focus();
}

function exportScorePackage() {
  const sequence = convert();
  if (!sequence) { toast("请先修正谱子错误。 "); return; }
  const metadata = validateScoreMetadata({
    title: elements.exportSongTitle.value,
    artist: elements.exportArtistName.value,
    sharedBy: elements.exportSharedBy.value,
    key: elements.keySignature.value,
    meter: elements.timeSignature.value,
    bpm: elements.bpm.value
  });
  if (metadata.error) { toast(metadata.error); return; }
  const exported = {
    format: SONG_FILE_FORMAT,
    version: SONG_FILE_VERSION,
    ...metadata.value,
    jianpu: sequenceToJianpu(sequence)
  };
  elements.macroName.value = metadata.value.title;
  elements.artistName.value = metadata.value.artist;
  currentScoreCredit = { artist: metadata.value.artist, sharedBy: metadata.value.sharedBy };
  download(`${JSON.stringify(exported, null, 2)}\n`, `${safeName().replace(/\s+/g, "-").toLowerCase() || "harmonica-score"}.harmonica-score.json`, "application/json");
  elements.scoreExportDialog.close();
  toast("谱子文件已下载。加入 QQ 群 1102489399 分享给维护者吧。 ");
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

let toastTimer;
function toast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => elements.toast.classList.remove("show"), 2400);
}

async function copyLua(sequence) {
  const lua = generateLua(sequence);
  try {
    await navigator.clipboard.writeText(lua);
    toast("Lua 已复制到剪贴板。");
  } catch {
    toast("浏览器未授权剪贴板；请使用下载功能。 ");
  }
}

[elements.score, elements.jianpuScore, elements.recordedScore].forEach((textarea) => textarea.addEventListener("input", () => { stopPreview(); updateLineNumbers(); convert(); }));
editorLineNumberPairs.forEach(([textarea, gutter]) => textarea.addEventListener("scroll", () => syncLineNumbers(textarea, gutter)));
elements.bpm.addEventListener("input", () => { stopPreview(); convert(); });
elements.convertButton.addEventListener("click", playPreview);
elements.importScoreButton.addEventListener("click", () => elements.importScoreInput.click());
elements.importScoreInput.addEventListener("change", () => importScorePackage(elements.importScoreInput.files?.[0]));
elements.macroExportButton.addEventListener("click", () => elements.macroExportSection.scrollIntoView({ behavior: "smooth", block: "start" }));
elements.exportScoreButton.addEventListener("click", openScoreExportDialog);
elements.confirmScoreExport.addEventListener("click", exportScorePackage);
elements.clearButton.addEventListener("click", () => {
  finishRecording({ apply: false });
  stopPreview();
  const activeEditor = inputMode === "jianpu" ? elements.jianpuScore : inputMode === "record" ? elements.recordedScore : elements.score;
  [elements.jianpuScore, elements.recordedScore, elements.score].forEach((editor) => { editor.value = ""; });
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
elements.restartButton.addEventListener("click", () => playPreview());
elements.stopButton.addEventListener("click", stopPreview);
elements.volume.addEventListener("input", () => {
  if (audioContext && masterGain) masterGain.gain.setTargetAtTime(Number(elements.volume.value) / 100, audioContext.currentTime, 0.01);
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
elements.inputModeButtons.forEach((button) => button.addEventListener("click", () => setInputMode(button.dataset.inputMode)));
elements.songSearch.addEventListener("input", () => renderSongLibrary(elements.songSearch.value));
elements.songGrid.addEventListener("click", (event) => {
  const card = event.target.closest("[data-song-index]");
  if (!card) return;
  loadSong(SONG_LIBRARY[Number(card.dataset.songIndex)]);
});
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

renderSongLibrary();
updateLineNumbers();
setInputMode("jianpu", { force: true, silent: true });
if (SONG_LIBRARY[0]) loadSong(SONG_LIBRARY[0]);
window.addEventListener("resize", scheduleWorkbenchHeightSync);
if (typeof ResizeObserver === "function") {
  new ResizeObserver(scheduleWorkbenchHeightSync).observe(elements.editorPanel);
}
if (typeof MutationObserver === "function") {
  new MutationObserver(scheduleWorkbenchHeightSync).observe(elements.editorPanel, { attributes: true, childList: true, subtree: true });
}
scheduleWorkbenchHeightSync();
