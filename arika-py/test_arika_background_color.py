import unittest
from types import SimpleNamespace
from arika_webgpu import (background_clear_color,srgb_to_linear,linear_to_srgb,
                         DEFAULT_BACKGROUND,c_webgpu_renderer)


class BackgroundColorTests(unittest.TestCase):
    def test_picked_colors_round_trip_through_srgb_attachment(self):
        for rgb in ((32,162,212),(128,128,128),(51,102,153),(0,0,0),(255,255,255),(255,0,128)):
            picked=tuple(v/255 for v in rgb)+(.4,)
            clear=background_clear_color(picked,'bgra8unorm-srgb')
            display=tuple(round(linear_to_srgb(v)*255) for v in clear[:3])
            self.assertEqual(display,rgb)
            self.assertEqual(clear[3],.4)
            self.assertEqual(background_clear_color(picked,'rgba8unorm'),picked)

    def test_transfer_thresholds_and_default(self):
        self.assertAlmostEqual(srgb_to_linear(.5),.21404114048223255)
        self.assertAlmostEqual(srgb_to_linear(.01),.01/12.92)
        self.assertAlmostEqual(linear_to_srgb(.001),.01292)
        for actual,expected in zip(background_clear_color(DEFAULT_BACKGROUND,'rgba8unorm-srgb'),(.035,.045,.06,1)):
            self.assertAlmostEqual(actual,expected)

    def test_render_pass_receives_format_correct_clear_value(self):
        # Capture the actual render-pass descriptor, without needing an adapter.
        for texture_format in ('bgra8unorm-srgb','rgba8unorm'):
            captured={}
            render=SimpleNamespace(set_bind_group=lambda *a:None,end=lambda:None)
            def begin(**descriptor):captured.update(descriptor);return render
            encoder=SimpleNamespace(begin_render_pass=begin,finish=lambda:None)
            queue=SimpleNamespace(write_buffer=lambda *a:None,submit=lambda *a:None)
            renderer=c_webgpu_renderer.__new__(c_webgpu_renderer)
            renderer.m_device=SimpleNamespace(queue=queue,create_command_encoder=lambda:encoder)
            renderer.m_project=None;renderer.m_format=texture_format;renderer.m_size=(1,1)
            texture=SimpleNamespace(create_view=lambda:None)
            renderer.m_depth=texture;renderer.m_pick=texture
            renderer.m_camera=None;renderer.m_camera_group=None
            color=(32/255,162/255,212/255,1)
            renderer.render(1,1,0,0,[0,0,0],10,target=texture,options={'background':color})
            self.assertEqual(captured['color_attachments'][0]['clear_value'],background_clear_color(color,texture_format))
