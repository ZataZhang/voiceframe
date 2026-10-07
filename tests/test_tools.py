"""Offline regression coverage for the skill's reusable tools."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/voiceframe/scripts'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Tools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)

    def write(self, name, value):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def run_tool(self, name, *args, **kwargs):
        return subprocess.run([sys.executable, str(SCRIPTS / f'{name}.py'),
                               '--project', str(self.project), *args],
                              capture_output=True, text=True, timeout=10, **kwargs)

    def test_offline_cues_and_invalid_limit(self):
        self.write('audio_meta.json', {'voices': [
            {'line': 1, 'text': '测试第一句。测试第二句。', 'start': 5, 'duration': 4}]})
        result = self.run_tool('gen_cues')
        self.assertEqual(result.returncode, 0, result.stderr)
        cues = json.loads((self.project / 'cues.json').read_text())['1']
        self.assertEqual(cues[0]['t'], 5)
        self.assertAlmostEqual(cues[-1]['t'] + cues[-1]['d'], 9, places=3)
        self.assertNotEqual(self.run_tool('gen_cues', '--max-chars', '0').returncode, 0)
        with self.assertRaises(ValueError):
            module('gen_cues').split_piece('长' * 100, 0)

    def test_asr_failure_does_not_reuse_stale_file(self):
        self.write('asr-raw.json', {'transcripts': [{'sentences': []}]})
        audio = self.project / 'assets/voice/master-oneshot.wav'
        audio.parent.mkdir(parents=True)
        audio.touch()
        executable = self.project / 'bl'
        executable.write_text('#!/bin/sh\nexit 1\n')
        executable.chmod(0o755)
        env = {**os.environ, 'PATH': str(self.project) + os.pathsep + os.environ['PATH']}
        result = self.run_tool('gen_cues', '--asr', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.project / 'cues-asr.json').exists())
        self.assertIn('ASR failed', result.stderr)

    def test_asr_reuse(self):
        audio = self.project / 'assets/voice/master-oneshot.wav'
        audio.parent.mkdir(parents=True)
        audio.touch()
        self.write('asr-raw.json', {'transcripts': [{'sentences': [
            {'text': '同步测试', 'begin_time': 1200, 'end_time': 2500}]}]})
        result = self.run_tool('gen_cues', '--asr', '--reuse')
        self.assertEqual(result.returncode, 0, result.stderr)
        cues = json.loads((self.project / 'cues-asr.json').read_text())
        self.assertEqual(cues, [{'text': '同步测试', 't': 1.2, 'd': 1.3}])

    def test_svg_conversion_retains_color_and_source(self):
        source = self.project / 'fig.svg'
        content = '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="white"/><text>测试</text><path stroke="#ff6600"/><style>.axis {stroke: #000}</style></svg>'
        source.write_text(content)
        output = self.project / 'dark'
        result = subprocess.run([sys.executable, str(SCRIPTS / 'darken_figures.py'),
                                 '--input', str(source), '--output', str(output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(source.read_text(), content)
        tree = ET.parse(output / 'fig.svg')
        self.assertEqual(tree.getroot().get('fill'), '#f0ece5')
        self.assertEqual(list(tree.getroot())[0].get('fill'), '#111111')
        self.assertEqual(list(tree.getroot())[2].get('stroke'), '#ff6600')
        self.assertIn('#f0ece5', list(tree.getroot())[3].text)

    def test_cross_frame_cues(self):
        tools = module('build_frames')
        cue = [{'text': '跨帧字幕', 't': 12.9, 'd': 0.2}]
        self.assertEqual(tools.cues_in_window(cue, 5, 13)[0]['t'], 7.9)
        second = tools.cues_in_window(cue, 13, 20)[0]
        self.assertEqual(second['t'], 0)
        self.assertAlmostEqual(second['d'], 0.1)

    def prepare_frames(self):
        self.write('audio_meta.json', {'voices': [
            {'line': 1, 'text': '第一句', 'start': 5, 'duration': 21},
            {'line': 2, 'text': '第二句', 'start': 27, 'duration': 3}]})
        self.write('cues.json', {'1': [{'text': '第一句', 't': 5, 'd': 21}],
                                '2': [{'text': '第二句', 't': 27, 'd': 3}]})
        self.write('titles.json', {'1': '标题一', '2': '标题二'})
        self.write('frames.config.json', {'pools': {'demo': ['test.mp4']},
            'rotation': ['demo'], 'quote_pool': 'demo', 'chapters': {},
            'figures': {'assets/dark/fig.svg': {'frames': [1], 'label': '图', 'caption': '图注'}}})
        asset = self.project / 'assets/broll/test.mp4'
        asset.parent.mkdir(parents=True)
        asset.touch()
        figure = self.project / 'assets/dark/fig.svg'
        figure.parent.mkdir(parents=True)
        figure.write_text('<svg/>')

    def test_frames_use_audio_start_and_keep_title_ownership(self):
        self.prepare_frames()
        dry = self.run_tool('build_frames', '--dry-run')
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse((self.project / 'compositions').exists())
        result = self.run_tool('build_frames')
        self.assertEqual(result.returncode, 0, result.stderr)
        frames = json.loads((self.project / 'frames.json').read_text())
        self.assertEqual([f['t0'] for f in frames], [5, 15.5, 27])
        self.assertEqual([f['screen_title'] for f in frames], ['标题一', None, '标题二'])
        for frame in frames:
            html = (self.project / 'compositions/frames' / frame['file']).read_text()
            self.assertIn(f'id="{frame["composition_id"]}"', html)
            self.assertIn(f'window.__timelines["{frame["composition_id"]}"]', html)
            self.assertIn('class="subs"', html)
        (self.project / 'assets/broll/test.mp4').unlink()
        self.assertNotEqual(self.run_tool('build_frames', '--dry-run').returncode, 0)

    def test_template_registers_timeline_and_has_unique_ids(self):
        template = ROOT / 'skills/voiceframe/assets/adapters/hyperframes/compositions/frames/frame.html.template'
        html = template.read_text().replace('FRAME_ID', 'f01').replace('DURATION_NUMBER', '6').replace('DURATION', '6')
        ids = re.findall(r'(?<![\w-])id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))
        script = re.findall(r'<script>(.*?)</script>', html, re.S)[0]
        stub = ('var ids=' + json.dumps(ids) + ';var window={};'
                'var document={getElementById:id=>ids.includes(id)?{id}:null};'
                'var timeline={set(){},fromTo(){},to(){}};'
                'var gsap={timeline:()=>timeline};')
        check = '\nif(!window.__timelines || !window.__timelines.f01) process.exit(1);'
        result = subprocess.run(['node', '-e', stub + script + check], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
