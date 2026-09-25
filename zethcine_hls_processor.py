import os
import sys
import json
import shutil
import subprocess
from pathlib import Path


# ============================================================
# ZETHCINE - GERADOR HLS MULTIQUALIDADE
#
#
# fMP4 / CMAF / HLS VOD
#
# Intel Quick Sync / QSV
#
# REGRA 4K:
#
# Se o vídeo original tiver resolução 4K:
#   3840x2160 ou maior
#
# será gerada a variante:
#   2160p / 3840x2160
#
# Se o vídeo original NÃO for 4K:
#   NÃO será feito upscale para 4K.
#
# ============================================================


FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


# ============================================================
# CONFIGURAÇÕES
# ============================================================

SEGMENT_TIME = 6


# ============================================================
# QUALIDADE 4K
# ============================================================

QUALITY_4K = {
    "name": "2160p",
    "width": 3840,
    "height": 2160,
    "bitrate": "18000k",
    "maxrate": "20000k",
    "bufsize": "28000k",
    "bandwidth": 20000000,
    "average_bandwidth": 18000000,
}


# ============================================================
# QUALIDADES PADRÃO
# ============================================================

STANDARD_QUALITIES = [
    {
        "name": "1080p",
        "width": 1920,
        "height": 1080,
        "bitrate": "7500k",
        "maxrate": "8500k",
        "bufsize": "12000k",
        "bandwidth": 8500000,
        "average_bandwidth": 7500000,
    },
    {
        "name": "720p",
        "width": 1280,
        "height": 720,
        "bitrate": "3800k",
        "maxrate": "4300k",
        "bufsize": "6000k",
        "bandwidth": 4300000,
        "average_bandwidth": 3800000,
    },
    {
        "name": "480p",
        "width": 854,
        "height": 480,
        "bitrate": "1200k",
        "maxrate": "1400k",
        "bufsize": "2000k",
        "bandwidth": 1400000,
        "average_bandwidth": 1200000,
    },
    {
        "name": "360p",
        "width": 640,
        "height": 360,
        "bitrate": "800k",
        "maxrate": "900k",
        "bufsize": "1200k",
        "bandwidth": 900000,
        "average_bandwidth": 800000,
    },
]


# ============================================================
# UTILITÁRIOS
# ============================================================

def command_exists(command):

    return shutil.which(command) is not None


def safe_name(text):

    chars = '<>:"/\\|?*'

    for char in chars:
        text = text.replace(char, "_")

    return text.strip()


def yes_answer(value):

    return value.strip().lower() in [
        "s",
        "sim",
        "y",
        "yes",
    ]


def run_capture(command):

    print()
    print("Executando:")

    print(
        " ".join(
            f'"{x}"' if " " in str(x) else str(x)
            for x in command
        )
    )

    print()

    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def format_seconds(value):

    if value is None:
        return "N/A"

    return f"{float(value):.3f}s"


# ============================================================
# FFPROBE
# ============================================================

def probe_media(url):

    command = [
        FFPROBE,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        url,
    ]

    result = run_capture(command)

    if result.returncode != 0:

        print()
        print("=" * 70)
        print("ERRO AO ANALISAR O ARQUIVO")
        print("=" * 70)
        print()

        print(result.stderr)

        sys.exit(1)

    try:

        return json.loads(
            result.stdout
        )

    except Exception:

        print()
        print(
            "ERRO: FFprobe retornou "
            "dados inválidos."
        )

        print(
            result.stdout[:2000]
        )

        sys.exit(1)


# ============================================================
# DURAÇÃO
# ============================================================

def get_media_duration(data):

    format_data = data.get(
        "format",
        {}
    )

    duration = format_data.get(
        "duration"
    )

    try:

        duration = float(
            duration
        )

        if duration > 0:

            return duration

    except Exception:

        pass

    durations = []

    for stream in data.get(
        "streams",
        []
    ):

        value = stream.get(
            "duration"
        )

        try:

            value = float(
                value
            )

            if value > 0:

                durations.append(
                    value
                )

        except Exception:

            continue

    if durations:

        return max(durations)

    return None


# ============================================================
# SELEÇÃO DO ÁUDIO
# ============================================================

def find_portuguese_audio(streams):

    audio_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    if not audio_streams:

        print(
            "ERRO: nenhum áudio encontrado."
        )

        sys.exit(1)

    print()
    print("=" * 70)
    print("ÁUDIOS ENCONTRADOS")
    print("=" * 70)
    print()

    for relative_index, stream in enumerate(
        audio_streams
    ):

        global_index = stream.get(
            "index"
        )

        language = (
            stream
            .get("tags", {})
            .get("language", "N/A")
        )

        title = (
            stream
            .get("tags", {})
            .get("title", "N/A")
        )

        codec = stream.get(
            "codec_name",
            "N/A"
        )

        default = (
            stream
            .get("disposition", {})
            .get("default", 0)
        )

        start_time = stream.get(
            "start_time",
            "0.000000"
        )

        try:

            start_time_float = float(
                start_time
            )

        except Exception:

            start_time_float = 0.0

        print(
            f"[áudio {relative_index}] "
            f"global={global_index} | "
            f"idioma={language} | "
            f"titulo={title} | "
            f"codec={codec} | "
            f"stream_start={start_time_float:.6f}s | "
            f"default={default}"
        )

    # --------------------------------------------------------
    # PRIORIDADE POR IDIOMA
    # --------------------------------------------------------

    priorities = [
        "por",
        "pt",
        "por-br",
        "pt-br",
    ]

    for priority in priorities:

        for relative_index, stream in enumerate(
            audio_streams
        ):

            language = (
                stream
                .get("tags", {})
                .get("language", "")
                .lower()
                .strip()
            )

            if language == priority:

                return {
                    "global_index": stream["index"],
                    "relative_index": relative_index,
                }

    # --------------------------------------------------------
    # PRIORIDADE POR TÍTULO
    # --------------------------------------------------------

    keywords = [
        "portugu",
        "brasil",
        "brazil",
        "pt-br",
        "portuguese",
    ]

    for relative_index, stream in enumerate(
        audio_streams
    ):

        title = (
            stream
            .get("tags", {})
            .get("title", "")
            .lower()
        )

        if any(
            keyword in title
            for keyword in keywords
        ):

            return {
                "global_index": stream["index"],
                "relative_index": relative_index,
            }

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    for relative_index, stream in enumerate(
        audio_streams
    ):

        disposition = stream.get(
            "disposition",
            {}
        )

        if disposition.get(
            "default"
        ) == 1:

            return {
                "global_index": stream["index"],
                "relative_index": relative_index,
            }

    # --------------------------------------------------------
    # PRIMEIRO ÁUDIO
    # --------------------------------------------------------

    stream = audio_streams[0]

    return {
        "global_index": stream["index"],
        "relative_index": 0,
    }


# ============================================================
# INFORMAÇÕES DO ÁUDIO
# ============================================================

def get_audio_info(
    streams,
    audio_index
):

    for stream in streams:

        if stream.get(
            "index"
        ) == audio_index:

            start_time = stream.get(
                "start_time",
                "0.000000"
            )

            try:

                start_time_float = float(
                    start_time
                )

            except Exception:

                start_time_float = 0.0

            return {
                "index": audio_index,
                "start_time": start_time_float,
                "language": (
                    stream
                    .get("tags", {})
                    .get("language", "N/A")
                ),
                "title": (
                    stream
                    .get("tags", {})
                    .get("title", "N/A")
                ),
                "codec": stream.get(
                    "codec_name",
                    "N/A"
                ),
                "sample_rate": stream.get(
                    "sample_rate",
                    "N/A"
                ),
                "channels": stream.get(
                    "channels",
                    "N/A"
                ),
            }

    return {
        "index": audio_index,
        "start_time": 0,
        "language": "N/A",
        "title": "N/A",
        "codec": "N/A",
        "sample_rate": "N/A",
        "channels": "N/A",
    }


# ============================================================
# INFORMAÇÕES DO VÍDEO
# ============================================================

def get_video_info(streams):

    videos = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
        and stream.get("codec_name") != "mjpeg"
    ]

    if not videos:

        print(
            "ERRO: nenhum vídeo válido encontrado."
        )

        sys.exit(1)

    video = videos[0]

    width = int(
        video.get(
            "width",
            0
        )
    )

    height = int(
        video.get(
            "height",
            0
        )
    )

    fps_string = video.get(
        "r_frame_rate",
        "0/1"
    )

    try:

        numerator, denominator = (
            fps_string.split("/")
        )

        fps = (
            float(numerator) /
            float(denominator)
        )

    except Exception:

        fps = 23.976

    if fps <= 0:

        fps = 23.976

    start_time = video.get(
        "start_time",
        "0.000000"
    )

    try:

        video_start_time = float(
            start_time
        )

    except Exception:

        video_start_time = 0.0

    return (
        video,
        width,
        height,
        fps,
        video_start_time,
    )


# ============================================================
# DETECTA 4K
# ============================================================

def is_4k_source(
    width,
    height
):

    # --------------------------------------------------------
    # Consideramos 4K quando:
    #
    # largura >= 3840
    # E
    # altura >= 2160
    #
    # Dessa forma:
    #
    # 3840x2160 -> 4K
    # 4096x2160 -> 4K
    # 3840x2170 -> 4K
    #
    # 2560x1440 -> NÃO
    # 1920x1080 -> NÃO
    # --------------------------------------------------------

    return (
        width >= 3840
        and
        height >= 2160
    )


# ============================================================
# MONTA LISTA DE QUALIDADES
# ============================================================

def build_qualities(
    source_width,
    source_height
):

    qualities = []

    # --------------------------------------------------------
    # 4K
    #
    # SOMENTE se a fonte for realmente 4K.
    # --------------------------------------------------------

    source_is_4k = is_4k_source(
        source_width,
        source_height
    )

    if source_is_4k:

        qualities.append(
            QUALITY_4K.copy()
        )

    # --------------------------------------------------------
    # QUALIDADES PADRÃO
    # --------------------------------------------------------

    for quality in STANDARD_QUALITIES:

        qualities.append(
            quality.copy()
        )

    return qualities


# ============================================================
# FILTRO DE VÍDEO
# ============================================================

def build_video_filter(
    width,
    height
):

    return (
        f"scale={width}:{height}:"
        f"force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:"
        f"(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1"
    )


# ============================================================
# GERA UMA VARIANTE
# ============================================================

def generate_variant(
    input_url,
    output_dir,
    quality,
    audio_index,
    fps
):

    quality_name = quality["name"]

    quality_dir = (
        Path(output_dir) /
        quality_name
    )

    quality_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    playlist_name = "playlist.m3u8"

    init_name = "init.mp4"

    segment_name = (
        "segment_%05d.m4s"
    )

    filter_expression = build_video_filter(
        quality["width"],
        quality["height"]
    )

    # ========================================================
    # GOP
    #
    # 6 segundos x FPS
    # ========================================================

    gop = round(
        fps *
        SEGMENT_TIME
    )

    if gop < 24:

        gop = 144

    print()
    print("=" * 70)
    print(
        f"GERANDO {quality_name}"
    )
    print("=" * 70)
    print()

    print(
        f"Resolução : "
        f"{quality['width']}x"
        f"{quality['height']}"
    )

    print(
        f"Bitrate   : "
        f"{quality['bitrate']}"
    )

    print(
        f"Maxrate   : "
        f"{quality['maxrate']}"
    )

    print(
        f"FPS       : "
        f"{fps:.3f}"
    )

    print(
        f"GOP       : "
        f"{gop}"
    )

    print(
        f"Segmento  : "
        f"{SEGMENT_TIME}s"
    )

    print(
        f"Áudio     : "
        f"stream global {audio_index}"
    )

    print(
        f"Pasta     : "
        f"{quality_dir}"
    )

    print()

    # ========================================================
    # COMANDO FFMPEG
    # ========================================================

    command = [
        FFMPEG,

        "-hide_banner",
        "-y",

        "-i",
        input_url,

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        "-map",
        "0:v:0",

        "-vf",
        filter_expression,

        # ----------------------------------------------------
        # QSV
        # ----------------------------------------------------

        "-c:v",
        "h264_qsv",

        "-pix_fmt",
        "nv12",

        "-profile:v",
        "high",

        "-level",
        "4.1",

        "-b:v",
        quality["bitrate"],

        "-maxrate",
        quality["maxrate"],

        "-bufsize",
        quality["bufsize"],

        # ----------------------------------------------------
        # GOP / IDR
        # ----------------------------------------------------

        "-g",
        str(gop),

        "-forced-idr",
        "1",

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        "-map",
        f"0:{audio_index}",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "48000",

        "-ac",
        "2",

        # ----------------------------------------------------
        # HLS
        # ----------------------------------------------------

        "-f",
        "hls",

        "-hls_time",
        str(SEGMENT_TIME),

        "-hls_playlist_type",
        "vod",

        "-hls_segment_type",
        "fmp4",

        "-hls_fmp4_init_filename",
        init_name,

        "-hls_segment_filename",
        segment_name,

        "-hls_flags",
        "independent_segments",

        playlist_name,
    ]

    print(
        "Executando FFmpeg..."
    )

    print()

    result = subprocess.run(
        command,
        cwd=str(quality_dir)
    )

    if result.returncode != 0:

        print()
        print("=" * 70)
        print(
            f"[ERRO] FFmpeg falhou em "
            f"{quality_name}"
        )
        print("=" * 70)

        print(
            f"Código: "
            f"{result.returncode}"
        )

        return False

    # ========================================================
    # ARQUIVOS
    # ========================================================

    playlist = (
        quality_dir /
        playlist_name
    )

    init_file = (
        quality_dir /
        init_name
    )

    segments = list(
        quality_dir.glob(
            "segment_*.m4s"
        )
    )

    if not playlist.exists():

        print(
            f"[ERRO] {quality_name}: "
            "playlist não criada."
        )

        return False

    if not init_file.exists():

        print(
            f"[ERRO] {quality_name}: "
            "init.mp4 não criado."
        )

        return False

    if len(segments) == 0:

        print(
            f"[ERRO] {quality_name}: "
            "nenhum segmento criado."
        )

        return False

    print()
    print(
        f"[OK] {quality_name} concluído"
    )

    print(
        f"     Playlist : "
        f"{playlist}"
    )

    print(
        f"     Init     : "
        f"{init_file}"
    )

    print(
        f"     Segmentos: "
        f"{len(segments)}"
    )

    return True


# ============================================================
# CRIA MASTER PLAYLIST
# ============================================================

def create_master_playlist(
    output_dir,
    qualities
):

    output_dir = Path(
        output_dir
    )

    master = (
        output_dir /
        "master.m3u8"
    )

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "",
    ]

    # --------------------------------------------------------
    # Ordem:
    #
    # 2160p
    # 1080p
    # 720p
    # 480p
    # 360p
    # --------------------------------------------------------

    for quality in qualities:

        name = quality["name"]

        width = quality["width"]
        height = quality["height"]

        bandwidth = quality["bandwidth"]
        average_bandwidth = (
            quality["average_bandwidth"]
        )

        lines.append(
            "#EXT-X-STREAM-INF:"
            f"BANDWIDTH={bandwidth},"
            f"AVERAGE-BANDWIDTH={average_bandwidth},"
            f"RESOLUTION={width}x{height},"
            'CODECS="avc1.640028,mp4a.40.2"'
        )

        lines.append(
            f"{name}/playlist.m3u8"
        )

        lines.append("")

    content = "\n".join(
        lines
    )

    master.write_text(
        content,
        encoding="utf-8"
    )

    print()
    print(
        "[OK] master.m3u8 criado"
    )

    print()

    for quality in qualities:

        print(
            f"     {quality['name']} "
            f"{quality['width']}x"
            f"{quality['height']}"
        )


# ============================================================
# VALIDA PLAYLIST
# ============================================================

def validate_playlist(
    playlist_path
):

    playlist_path = Path(
        playlist_path
    )

    if not playlist_path.exists():

        return False, (
            "playlist não existe"
        )

    try:

        content = playlist_path.read_text(
            encoding="utf-8"
        )

    except Exception as error:

        return False, (
            f"não foi possível ler: "
            f"{error}"
        )

    # --------------------------------------------------------
    # MAP
    # --------------------------------------------------------

    if "#EXT-X-MAP:" not in content:

        return False, (
            "playlist não possui "
            "EXT-X-MAP"
        )

    # --------------------------------------------------------
    # CAMINHOS ABSOLUTOS
    # --------------------------------------------------------

    if ":\\" in content:

        return False, (
            "playlist contém caminho "
            "absoluto do Windows"
        )

    if "C:/" in content:

        return False, (
            "playlist contém caminho "
            "absoluto do Windows"
        )

    for line in content.splitlines():

        line = line.strip()

        if line.startswith("/"):

            return False, (
                "playlist contém caminho "
                "absoluto"
            )

    # --------------------------------------------------------
    # INIT
    # --------------------------------------------------------

    if 'URI="init.mp4"' not in content:

        return False, (
            'playlist não aponta para '
            '"init.mp4"'
        )

    # --------------------------------------------------------
    # SEGMENTOS
    # --------------------------------------------------------

    if "segment_" not in content:

        return False, (
            "playlist não possui "
            "segmentos"
        )

    # --------------------------------------------------------
    # DURAÇÃO DOS SEGMENTOS
    #
    # Aceitamos até 2x o tamanho alvo.
    #
    # Para 6s:
    # máximo aceitável = 12s
    # --------------------------------------------------------

    max_allowed = SEGMENT_TIME * 2

    durations = []

    for line in content.splitlines():

        line = line.strip()

        if line.startswith(
            "#EXTINF:"
        ):

            try:

                value = line[
                    len("#EXTINF:"):
                ]

                value = value.split(
                    ","
                )[0]

                duration = float(
                    value
                )

                durations.append(
                    duration
                )

            except Exception:

                continue

    if not durations:

        return False, (
            "nenhuma duração EXTINF "
            "encontrada"
        )

    maximum = max(
        durations
    )

    if maximum > max_allowed:

        return False, (
            f"segmentos inválidos: "
            f"máximo encontrado "
            f"{maximum:.3f}s; "
            f"esperado aproximadamente "
            f"{SEGMENT_TIME}s"
        )

    return True, "OK"


# ============================================================
# VALIDA SAÍDA
# ============================================================

def validate_output(
    output_dir,
    qualities
):

    output_dir = Path(
        output_dir
    )

    print()
    print("=" * 70)
    print("VALIDANDO SAÍDA")
    print("=" * 70)
    print()

    valid = True

    # ========================================================
    # MASTER
    # ========================================================

    master = (
        output_dir /
        "master.m3u8"
    )

    if master.exists():

        print(
            "[OK] master.m3u8"
        )

        try:

            master_content = (
                master.read_text(
                    encoding="utf-8"
                )
            )

            required_variants = []

            for quality in qualities:

                required_variants.append(
                    f"{quality['name']}/playlist.m3u8"
                )

            for variant in required_variants:

                if variant not in master_content:

                    print(
                        f"[ERRO] master não "
                        f"possui {variant}"
                    )

                    valid = False

        except Exception as error:

            print(
                "[ERRO] não foi possível "
                "ler master.m3u8"
            )

            print(error)

            valid = False

    else:

        print(
            "[ERRO] Faltando: "
            "master.m3u8"
        )

        valid = False

    # ========================================================
    # QUALIDADES
    # ========================================================

    for quality in qualities:

        name = quality["name"]

        folder = (
            output_dir /
            name
        )

        playlist = (
            folder /
            "playlist.m3u8"
        )

        init = (
            folder /
            "init.mp4"
        )

        if not folder.exists():

            print(
                f"[ERRO] Pasta "
                f"{name} não existe"
            )

            valid = False

            continue

        # ----------------------------------------------------
        # PLAYLIST
        # ----------------------------------------------------

        if playlist.exists():

            print(
                f"[OK] "
                f"{name}/playlist.m3u8"
            )

            playlist_ok, message = (
                validate_playlist(
                    playlist
                )
            )

            if playlist_ok:

                print(
                    "     [OK] "
                    "Segmentos com duração válida"
                )

            else:

                print(
                    f"     [ERRO] "
                    f"{message}"
                )

                valid = False

        else:

            print(
                f"[ERRO] Faltando: "
                f"{name}/playlist.m3u8"
            )

            valid = False

        # ----------------------------------------------------
        # INIT
        # ----------------------------------------------------

        if init.exists():

            size_mb = (
                init.stat().st_size /
                1024 /
                1024
            )

            print(
                f"[OK] "
                f"{name}/init.mp4 "
                f"({size_mb:.2f} MB)"
            )

        else:

            print(
                f"[ERRO] Faltando: "
                f"{name}/init.mp4"
            )

            valid = False

        # ----------------------------------------------------
        # SEGMENTOS
        # ----------------------------------------------------

        segments = list(
            folder.glob(
                "segment_*.m4s"
            )
        )

        if len(segments) > 0:

            print(
                f"[OK] "
                f"{name}: "
                f"{len(segments)} segmentos"
            )

        else:

            print(
                f"[ERRO] "
                f"{name}: nenhum "
                "segmento encontrado"
            )

            valid = False

    return valid


# ============================================================
# MOSTRA ESTRUTURA
# ============================================================

def show_structure(
    output_dir,
    qualities
):

    output_dir = Path(
        output_dir
    )

    print()
    print("=" * 70)
    print("ESTRUTURA FINAL")
    print("=" * 70)
    print()

    print(
        f"{output_dir.name}/"
    )

    print(
        "├── master.m3u8"
    )

    for index, quality in enumerate(
        qualities
    ):

        name = quality["name"]

        if index == len(
            qualities
        ) - 1:

            branch = "└──"

        else:

            branch = "├──"

        print(
            f"{branch} {name}/"
        )

        print(
            "    ├── playlist.m3u8"
        )

        print(
            "    ├── init.mp4"
        )

        print(
            "    └── segment_*.m4s"
        )

    print()


# ============================================================
# MOSTRA PLAYLIST
# ============================================================

def show_playlist_sample(
    output_dir
):

    print()
    print("=" * 70)
    print("VERIFICAÇÃO DO PLAYLIST 1080P")
    print("=" * 70)
    print()

    playlist = (
        Path(output_dir) /
        "1080p" /
        "playlist.m3u8"
    )

    if not playlist.exists():

        print(
            "Playlist 1080p não encontrada."
        )

        return

    try:

        lines = playlist.read_text(
            encoding="utf-8"
        ).splitlines()

    except Exception:

        print(
            "Não foi possível ler "
            "o playlist."
        )

        return

    for line in lines[:30]:

        print(line)

    if len(lines) > 30:

        print(
            "..."
        )

    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "       ZETHCINE - GERADOR HLS"
    )
    print(
        "       fMP4 / CMAF / VOD"
    )
    print(
        "       Intel Quick Sync / QSV"
    )
    print("=" * 70)
    print()

    # ========================================================
    # FFMPEG
    # ========================================================

    if not command_exists(
        FFMPEG
    ):

        print(
            "ERRO: FFmpeg não encontrado."
        )

        print(
            "Adicione a pasta bin do FFmpeg "
            "ao PATH."
        )

        sys.exit(1)

    # ========================================================
    # FFPROBE
    # ========================================================

    if not command_exists(
        FFPROBE
    ):

        print(
            "ERRO: FFprobe não encontrado."
        )

        sys.exit(1)

    # ========================================================
    # VERIFICA QSV
    # ========================================================

    print(
        "Verificando encoder H.264 QSV..."
    )

    qsv_check = run_capture([
        FFMPEG,
        "-hide_banner",
        "-encoders",
    ])

    if "h264_qsv" not in qsv_check.stdout:

        print()
        print(
            "ERRO: h264_qsv não está "
            "disponível neste FFmpeg."
        )

        sys.exit(1)

    print(
        "[OK] h264_qsv disponível"
    )

    # ========================================================
    # URL
    # ========================================================

    input_url = input(
        "\nCole a URL do vídeo original:\n> "
    ).strip()

    if not input_url:

        print(
            "URL inválida."
        )

        sys.exit(1)

    # ========================================================
    # NOME DA PASTA
    # ========================================================

    folder_name = input(
        "\nDigite o nome da pasta de saída:\n> "
    ).strip()

    if not folder_name:

        print(
            "Nome de pasta inválido."
        )

        sys.exit(1)

    folder_name = safe_name(
        folder_name
    )

    output_dir = (
        Path.cwd() /
        folder_name
    )

    # ========================================================
    # ANALISA ARQUIVO
    # ========================================================

    print()
    print(
        "Analisando arquivo..."
    )

    data = probe_media(
        input_url
    )

    streams = data.get(
        "streams",
        []
    )

    duration = get_media_duration(
        data
    )

    # ========================================================
    # VÍDEO
    # ========================================================

    (
        video,
        width,
        height,
        fps,
        video_start_time,
    ) = get_video_info(
        streams
    )

    # ========================================================
    # DETECTA 4K
    # ========================================================

    source_is_4k = is_4k_source(
        width,
        height
    )

    # ========================================================
    # MONTA QUALIDADES
    # ========================================================

    qualities = build_qualities(
        width,
        height
    )

    # ========================================================
    # ÁUDIO
    # ========================================================

    audio_selection = (
        find_portuguese_audio(
            streams
        )
    )

    audio_global_index = (
        audio_selection["global_index"]
    )

    audio_info = get_audio_info(
        streams,
        audio_global_index
    )

    # ========================================================
    # INFORMAÇÕES
    # ========================================================

    print()
    print("=" * 70)
    print("ANÁLISE FINAL")
    print("=" * 70)
    print()

    print(
        f"Resolução original : "
        f"{width}x{height}"
    )

    print(
        f"FPS                 : "
        f"{fps:.3f}"
    )

    print(
        f"Duração             : "
        f"{format_seconds(duration)}"
    )

    print(
        f"Vídeo stream start  : "
        f"{video_start_time:.6f}s"
    )

    print()

    # ========================================================
    # STATUS 4K
    # ========================================================

    print(
        "DETECÇÃO 4K:"
    )

    if source_is_4k:

        print(
            "  [SIM] Fonte original é 4K."
        )

        print(
            "  [OK] 2160p será gerado."
        )

    else:

        print(
            "  [NÃO] Fonte original não é 4K."
        )

        print(
            "  [OK] 2160p NÃO será gerado."
        )

        print(
            "  [OK] Nenhum upscale para 4K."
        )

    print()

    # ========================================================
    # ÁUDIO
    # ========================================================

    print(
        f"Áudio global        : "
        f"stream {audio_global_index}"
    )

    print(
        f"Áudio stream start  : "
        f"{audio_info['start_time']:.6f}s"
    )

    print(
        f"Codec áudio         : "
        f"{audio_info['codec']}"
    )

    print(
        f"Sample rate         : "
        f"{audio_info['sample_rate']}"
    )

    print(
        f"Canais              : "
        f"{audio_info['channels']}"
    )

    print()

    # ========================================================
    # QUALIDADES
    # ========================================================

    print(
        "QUALIDADES:"
    )

    for quality in qualities:

        print(
            f"  {quality['name']:<7}"
            f"{quality['width']}x"
            f"{quality['height']} "
            f"| {quality['bitrate']}"
        )

    print()

    print(
        f"Segmentos HLS       : "
        f"{SEGMENT_TIME}s"
    )

    print(
        "Formato              : "
        "fMP4 / CMAF"
    )

    print(
        "Vídeo                : "
        "H.264 High / Intel QSV"
    )

    print(
        "Áudio                : "
        "AAC 128 kbps / 48 kHz / Stereo"
    )

    print()

    print(
        "Pasta de saída:"
    )

    print(
        output_dir
    )

    print()

    # ========================================================
    # CONFIRMA
    # ========================================================

    confirm = input(
        "Iniciar processamento? (s/n): "
    )

    if not yes_answer(
        confirm
    ):

        print(
            "Processamento cancelado."
        )

        return

    # ========================================================
    # REMOVE PASTA EXISTENTE
    # ========================================================

    if output_dir.exists():

        print()
        print(
            "A pasta já existe."
        )

        overwrite = input(
            "Deseja substituir? (s/n): "
        )

        if not yes_answer(
            overwrite
        ):

            print(
                "Processamento cancelado."
            )

            return

        try:

            shutil.rmtree(
                output_dir
            )

        except Exception as error:

            print()
            print(
                "Não foi possível remover "
                "a pasta existente."
            )

            print(error)

            sys.exit(1)

    # ========================================================
    # CRIA PASTA
    # ========================================================

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # GERA QUALIDADES
    # ========================================================

    all_success = True

    for quality in qualities:

        success = generate_variant(
            input_url=input_url,
            output_dir=output_dir,
            quality=quality,
            audio_index=audio_global_index,
            fps=fps,
        )

        if not success:

            all_success = False

            break

    # ========================================================
    # ERRO
    # ========================================================

    if not all_success:

        print()
        print("=" * 70)
        print(
            "PROCESSAMENTO INTERROMPIDO"
        )
        print("=" * 70)
        print()

        print(
            "A pasta parcial foi mantida:"
        )

        print(
            output_dir
        )

        sys.exit(1)

    # ========================================================
    # MASTER
    # ========================================================

    create_master_playlist(
        output_dir,
        qualities
    )

    # ========================================================
    # VALIDA
    # ========================================================

    valid = validate_output(
        output_dir,
        qualities
    )

    # ========================================================
    # PLAYLIST
    # ========================================================

    show_playlist_sample(
        output_dir
    )

    # ========================================================
    # INVÁLIDO
    # ========================================================

    if not valid:

        print()
        print("=" * 70)
        print(
            "SAÍDA INVÁLIDA"
        )
        print("=" * 70)
        print()

        print(
            "NÃO faça upload desta pasta "
            "para o R2."
        )

        print()

        show_structure(
            output_dir,
            qualities
        )

        sys.exit(1)

    # ========================================================
    # SUCESSO
    # ========================================================

    print()
    print("=" * 70)
    print(
        "PROCESSAMENTO CONCLUÍDO"
    )
    print("=" * 70)
    print()

    print(
        "A estrutura está pronta "
        "para upload."
    )

    print()

    show_structure(
        output_dir,
        qualities
    )

    print()

    print(
        "MASTER:"
    )

    print(
        output_dir /
        "master.m3u8"
    )

    print()

    print(
        "IMPORTANTE:"
    )

    print(
        "Faça o upload mantendo "
        "EXATAMENTE essa estrutura "
        "de pastas."
    )

    print()

    print(
        "Exemplo:"
    )

    print(
        f"{folder_name}/master.m3u8"
    )

    if source_is_4k:

        print(
            f"{folder_name}/2160p/playlist.m3u8"
        )

        print(
            f"{folder_name}/2160p/init.mp4"
        )

        print(
            f"{folder_name}/2160p/segment_00000.m4s"
        )

    print(
        f"{folder_name}/1080p/playlist.m3u8"
    )

    print(
        f"{folder_name}/1080p/init.mp4"
    )

    print(
        f"{folder_name}/1080p/segment_00000.m4s"
    )

    print()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    main()