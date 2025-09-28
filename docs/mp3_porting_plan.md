# MP3 Subsystem Porting Plan

## Subsystem inventory
- **Runtime state and audio bus hookup (`src/lib/mp3.c`)** – `g_Mp3Vars` tracks ROM position, decode buffers, the env-mixer envelope, and the playback state machine. `mp3_make_samples` advances pan, pulls new decode blocks, emits the custom RSP commands (`0x08`/`0x07`), and feeds mono material through the env mixer before returning mixed samples to the main bus.【F:src/lib/mp3.c†L30-L321】
- **Streaming front-end (`src/lib/mp3/main.c`)** – `struct asistream` wraps the ROM DMA callback, MPEG header parser, side-information buffers, and six 576-sample PCM banks. `mp3main_read_frame` locks stream parameters to Layer 3, validates each frame, and fills the side-info tables. `mp3main_continue_file` rotates the decode buffers and stops playback cleanly on EOF or parse failures.【F:src/lib/mp3/main.c†L12-L230】
- **Decoder tables and transforms (`src/lib/mp3/decoder.c`)** – `mp3dec_init` precomputes sine windows, Huffman decode tables, and power/exponent lookup arrays that the IMDCT/rehuff stages use during playback.【F:src/lib/mp3/decoder.c†L2081-L2252】
- **Game-level glue (`src/lib/snd.c`)** – The sound driver keeps `g_SndCurMp3`, configures ROM addresses and metadata via `snd_start_mp3`, slews volume/pan from sequence data, and schedules follow-up chatter in `snd_tick`. Sequence players trigger clips through `snd_start_mp3_by_filenum`, while normal SFX requests short-circuit in `snd_start` when an MP3-tagged ID arrives.【F:src/lib/snd.c†L44-L2214】【F:src/lib/naudio/n_csplayer.c†L972-L999】
- **Asset tagging and priorities (`src/include/types.h`, `src/include/sfx.h`, `src/include/constants.h`)** – `union soundnumhack` encodes config flags, response type, and a 2-bit MP3 priority inside 16-bit sound IDs, while macros such as `MP3_LO_ZZ` layer those bits during content authoring. Response timers and state constants are defined alongside the rest of the audio enums.【F:src/include/types.h†L3429-L3443】【F:src/include/sfx.h†L2039-L2056】【F:src/include/constants.h†L2619-L2629】
- **Audio-mode awareness (`src/lib/alsurround.c`, `include/PR/n_libaudio.h`)** – The env-mixer path consults `var8009c340` to honour mono/headphone/surround settings, so ports must keep that control structure in sync with their audio-mode selector.【F:src/lib/alsurround.c†L15-L78】【F:include/PR/n_libaudio.h†L32-L76】

## External prerequisites
1. **RSP microcode ABI** – Perfect Dark emits custom commands `0x08` (`aMp3SetAddr`) and `0x07` (`aMp3ExecDma`) that are absent from Ocarina of Time’s stock `abi.h`. You’ll need matching macros, display-list opcodes, and microcode support so the RSP can DMA MP3 buffers into DMEM exactly like Perfect Dark does.【F:src/lib/mp3.c†L10-L249】
2. **Audio heap footprint** – `mp3_init` allocates the entire decoder workspace (≈140 KiB) from the audio heap at boot. Ensure the target’s heap budget can cover the `struct asistream`, Huffman tables, exponent tables, and env-mixer state before any other systems claim that memory.【F:src/lib/mp3.c†L44-L76】
3. **DMA callback plumbing** – The streaming layer reuses `n_syn->dma` for ROM reads. Whichever audio manager you port into must expose an equivalent DMA proc and honor the 0x400-byte prefetch window `mp3_dma` issues each audio frame.【F:src/lib/mp3.c†L374-L405】【F:src/lib/mp3/main.c†L22-L43】
4. **Audio-mode flags** – Keep the `var8009c340` structure and helpers synchronized so mono/headphone routing matches the target game’s expectations; `mp3_update_vars` references these flags whenever it slews pan or reconfigures the env mixer.【F:src/lib/mp3.c†L323-L365】【F:src/lib/alsurround.c†L20-L78】

## Recommended port order
1. **Extend the target ABI and microcode**
   - Add `aMp3SetAddr`/`aMp3ExecDma` (and the corresponding display-list macros) to the target’s audio ABI header, matching the command formats Perfect Dark uses.【F:src/lib/mp3.c†L10-L249】
   - Ensure the shipped RSP microcode recognises these opcodes and performs the same DMA/update sequence Rare’s version expects.

2. **Mirror the shared headers and state**
   - Import `struct mp3vars`, `struct asistream`, and the MP3 response/state enums so all modules agree on layout and behaviour.【F:src/include/types.h†L5586-L5620】【F:src/lib/mp3/mp3.h†L6-L87】【F:src/include/constants.h†L2619-L2629】
   - Carry over `union soundnumhack` and the MP3 tagging macros to preserve priority semantics for both scripted chatter and ambient music.【F:src/include/types.h†L3429-L3443】【F:src/include/sfx.h†L2039-L2056】

3. **Bring in the decoder and streaming core**
   - Port the entire `src/lib/mp3` directory: `mp3.c` (runtime driver), `main.c` (streaming/demux), `decoder.c` plus the hand-written assembly helpers (`lib_46650.s`, `lib_47550.s`, `util.s`). Their init paths are tightly coupled through `mp3main_init` and the shared lookup tables.【F:src/lib/mp3.c†L44-L321】【F:src/lib/mp3/main.c†L22-L230】【F:src/lib/mp3/decoder.c†L2081-L2252】
   - Confirm the target toolchain preserves the original calling conventions for the assembly files (Rare relied on them for IMDCT and polyphase filter performance).

4. **Integrate with the audio driver**
   - Call `mp3_init` after the audio heap is ready and before sequence banks claim memory. Replicate the `g_SndMp3Enabled` gating logic so the feature can be disabled on 4 MB builds if needed.【F:src/lib/snd.c†L1528-L1593】
   - Wire `mp3_make_samples` into the main audio bus so it runs before other mixers. Forward the driver’s DMA callback to `mp3_set_dma_func` so ROM fetches share the existing streaming infrastructure.【F:src/lib/mp3.c†L169-L405】

5. **Recreate the sound-system glue**
   - Port `snd_is_mp3`, `snd_start_mp3`, `snd_start_mp3_by_filenum`, `snd_stop_mp3`, and the `snd_tick` follow-up scheduler. These manage priority arbitration, ROM lookups, env-mixer setup, and the randomised whisper/acknowledge/greeting responses used by AI chatter.【F:src/lib/snd.c†L1888-L2214】【F:src/lib/snd.c†L1740-L1868】
   - Keep `g_SndCurMp3` intact so pause/resume and response timers behave identically across games.【F:src/lib/snd.c†L44-L2214】

6. **Hook up sequence control paths**
   - Update the sequence player to recognise `AL_MIDI_MP3_CTRL` (controller 0x1A) and forward those events to `snd_start_mp3_by_filenum`, matching Perfect Dark’s behaviour for scripted MP3 cues.【F:src/lib/naudio/n_csplayer.c†L972-L999】

7. **Adapt the asset pipeline**
   - Ensure ROM files are exposed through whatever lookup table Majora’s Mask uses so `file_get_rom_address`/`file_get_rom_size` equivalents return contiguous MP3 byte ranges.【F:src/lib/snd.c†L2187-L2196】
   - Preserve the macro-based tagging (eg. `MP3_ZZ`) when assigning IDs in the target’s sound tables so designers retain control over response types and priorities.【F:src/include/sfx.h†L2039-L2056】

8. **Match gameplay integration**
   - If the target game needs the conversational follow-up system, port the random-selection tables in `snd_tick`; otherwise, plan to disable or replace them once the core playback path is working.【F:src/lib/snd.c†L1740-L1868】
   - Audit any stage-specific hooks (eg. nose-dive and UFO ambience) to decide whether they should trigger MP3 assets in the new codebase.【F:src/lib/snd.c†L1740-L1868】

## Testing milestones
1. **Boot-time sanity checks** – Instrument `mp3_init` to verify all allocations succeed and that `mp3dec_init` seeds the Huffman/exponent tables (non-zero `var8009c6d8` / `var8009c6dc`). Dump buffer headers after init to confirm endian/layout assumptions.【F:src/lib/mp3.c†L44-L76】【F:src/lib/mp3/decoder.c†L2081-L2252】
2. **Stream validation** – Feed a known-good MP3 through `mp3main_start_file`/`mp3main_continue_file` under debugger control, ensuring frame headers stay stable and EOF flips the state to `MP3STATE_STOPPED`. This mirrors Perfect Dark’s failure handling path.【F:src/lib/mp3/main.c†L203-L230】【F:src/lib/mp3.c†L226-L253】
3. **Audio-thread integration** – During early bring-up, point `mp3_make_samples` at a scratch command buffer and verify it issues the expected sequence of `aMp3SetAddr`/`aMp3ExecDma`/`n_aLoadBuffer` calls for both mono and stereo assets.【F:src/lib/mp3.c†L226-L310】
4. **Volume/pan slewing** – Exercise `mp3_set_vol`/`mp3_set_pan` through the normal `snd_adjust` path to confirm the env mixer honours headphone/mono settings and that pan slews over multiple frames instead of snapping.【F:src/lib/snd.c†L1936-L2004】【F:src/lib/mp3.c†L180-L365】
5. **Sequence triggers and responses** – Trigger MP3 clips via MIDI controller 0x1A and through standard `snd_start` calls, confirming priority arbitration, follow-up chatter timers, and looping/stop conditions behave the same as Perfect Dark.【F:src/lib/naudio/n_csplayer.c†L972-L999】【F:src/lib/snd.c†L1740-L2214】
6. **Regression on non-MP3 audio** – After integrating the MP3 path, replay legacy ADPCM cues to ensure the new ABI commands and sound-number tagging do not interfere with the existing SFX/sequence pipeline.【F:src/lib/snd.c†L2099-L2135】【F:src/include/sfx.h†L2039-L2056】

Following this order keeps low-level dependencies (ABI, heap, DMA) in place before higher-level systems rely on them, making it easier to diagnose issues as you transplant the subsystem into Majora’s Mask or any other N64 title.
