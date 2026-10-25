"""Run with Ubuntu's /usr/bin/python3 to use its GI/GStreamer packages.

JSON status on stdout, line commands on stdin. Only explicitly selected audio
sources are opened. PAUSED uses the pipeline clock to exclude pause duration.
"""
import json
import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

def main():
    Gst.init(None)
    options = json.loads(sys.argv[1])
    if options.get('check'):
        names = ['pipewiresrc' if options['session'] == 'wayland' else 'ximagesrc', 'vp8enc', 'webmmux', 'videoconvert', 'videorate', 'videoscale', 'videobox', 'videocrop', 'pngenc']
        if options.get('audio'):
            names += ['pulsesrc', 'opusenc', 'audiomixer']
        missing = [name for name in names if not Gst.ElementFactory.find(name)]
        print(json.dumps({'missing': missing}), flush=True)
        return int(bool(missing))
    def quote(value):
        return json.dumps(str(value))
    source = (f'pipewiresrc fd={options["fd"]} path={quote(options["node"])} do-timestamp=true' if options['session'] == 'wayland' else 'ximagesrc use-damage=false show-pointer=true')
    if options.get('test_source'):
        source = 'videotestsrc is-live=true'
    if options.get('region') and options['session']=='x11':
        x, y, w, h = options['region']
        source += f' startx={x} starty={y} endx={x+w-1} endy={y+h-1}'
    pipeline = f'webmmux name=mux ! filesink location={quote(options["output"])} {source} ! queue ! videoconvert ! videorate ! video/x-raw,format=RGBA,framerate={options["fps"]}/1 ! '
    if options.get('region') and options['session']=='wayland':
        x,y,w,h = options['region']
        width,height = options['source_size']
        if x<0 or y<0 or w<2 or h<2 or x+w>width or y+h>height:
            raise ValueError('Recording area must fit inside the selected monitor.')
        pipeline += f'videocrop left={x} top={y} right={width-x-w} bottom={height-y-h} ! '
    if options.get('height'):
        pipeline += f'videoscale ! video/x-raw,height={options["height"]},pixel-aspect-ratio=1/1 ! '
    pipeline += 'videoconvert ! video/x-raw,format=I420 ! vp8enc deadline=1 cpu-used=8 threads=4 target-bitrate=' + str({'Low': 2000000, 'Medium': 5000000, 'High': 10000000}[options['quality']]) + ' ! queue ! mux. '
    if options['audio']:
        pipeline += 'audiomixer name=mix ! audioconvert ! audioresample ! opusenc ! queue ! mux. '
        for device in options['audio']:
            audio_source = 'audiotestsrc is-live=true' if options.get('test_source') else f'pulsesrc device={quote(device)} do-timestamp=true volume={options["volume"]}'
            pipeline += f'{audio_source} ! queue ! audioconvert ! audioresample ! mix. '
    if options.get('snapshot'):
        pipeline = f'{source} ! videoconvert ! pngenc snapshot=true ! filesink location={quote(options["output"])}'
    pipe = Gst.parse_launch(pipeline)
    loop = GLib.MainLoop()
    failed = False
    stopping = False
    def status(state):
        print(json.dumps({'state': state}), flush=True)
    def message(bus, msg):
        nonlocal failed
        if msg.type == Gst.MessageType.ERROR:
            error, _ = msg.parse_error()
            print(json.dumps({'error': str(error)}), flush=True)
            failed = True
            loop.quit()
        elif msg.type == Gst.MessageType.EOS:
            status('finished')
            loop.quit()
        elif msg.type == Gst.MessageType.STATE_CHANGED and msg.src == pipe:
            old, new, pending = msg.parse_state_changed()
            if new == Gst.State.PLAYING:
                status('preview' if options.get('snapshot') else 'recording')
            elif new == Gst.State.PAUSED and old == Gst.State.PLAYING:
                status('paused')
    bus = pipe.get_bus()
    bus.add_signal_watch()
    bus.connect('message', message)
    def command(channel, condition):
        nonlocal stopping
        line = sys.stdin.readline().strip() if not condition & GLib.IO_HUP else 'stop'
        if line == 'pause' and not stopping:
            pipe.set_state(Gst.State.PAUSED)
        elif line == 'resume' and not stopping:
            pipe.set_state(Gst.State.PLAYING)
        elif line == 'stop' and not stopping:
            stopping = True
            pipe.set_state(Gst.State.PLAYING)
            pipe.send_event(Gst.Event.new_eos())
            GLib.timeout_add_seconds(20, lambda: (loop.quit(), False)[1])
        return not bool(condition & GLib.IO_HUP)
    if not options.get("snapshot"):
        GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, command)
    pipe.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    finally:
        pipe.set_state(Gst.State.NULL)
    return int(failed)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), flush=True)
        sys.exit(1)
