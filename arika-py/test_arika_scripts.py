import struct
import unittest

import arika_scripts


def fixture():
    # One program: a string, command payload, variable, and symbol token.
    code = (struct.pack('<BI', 1, 3) + b'abc\0' +
            struct.pack('<BI', 2, (2 << 16) | 68) + b'xy' +
            struct.pack('<BI', 3, (4 << 16) | 2) +
            struct.pack('<BI', 4, ord('=')))
    program = struct.pack('<7I', 0, 5, len(code), 0, len(code), len(code), len(code)) + code
    return struct.pack('<II', 1, len(program)) + program + b'tail'


class ScriptTests(unittest.TestCase):
    def test_exact_roundtrip_variable_tokens_and_trailer(self):
        source = fixture()
        self.assertEqual(arika_scripts.rebuild(arika_scripts.parse(source)), source)

    def test_edit_same_size_string_and_command_payload(self):
        parsed = arika_scripts.parse(fixture())
        tokens = parsed['programs'][0]['tokens']
        tokens[0]['string_bytes_hex'] = b'def\0'.hex()
        tokens[1]['extra_hex'] = b'zz'.hex()
        rebuilt = arika_scripts.rebuild(parsed)
        self.assertIn(b'def\0', rebuilt)
        self.assertIn(b'zz', rebuilt)

    def test_reject_changed_token_extent(self):
        parsed = arika_scripts.parse(fixture())
        parsed['programs'][0]['tokens'][0]['string_bytes_hex'] = b'longer\0'.hex()
        with self.assertRaises(ValueError):
            arika_scripts.rebuild(parsed)

    def test_reject_bad_entrypoint(self):
        parsed = arika_scripts.parse(fixture())
        parsed['programs'][0]['entry_points'][0] = 1
        with self.assertRaises(ValueError):
            arika_scripts.rebuild(parsed)

    def test_reject_truncated_string(self):
        source = fixture()[:-8]
        with self.assertRaises(ValueError):
            arika_scripts.parse(source)


if __name__ == '__main__':
    unittest.main()
