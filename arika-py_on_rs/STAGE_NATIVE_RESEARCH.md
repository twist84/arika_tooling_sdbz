# Native stage loader findings

Reference SLES_541.61. Loader 0x23C8E0 confirms record strides: kinds 1/2 use 44 bytes; kind 3 adds eight bytes per reference; kinds 4/6 use 60; kind 5 uses 96. Child bit 1 and sibling bit 2 are read from the word at +2. Runtime bits 4/8 suppress repeated traversal. Kind 7 is also supported by native code (48 bytes), but absent from the supplied corpus and remains rejected by this parser.

Transform helper 0x23D3D0 copies translation at +8, computes quaternion from half-angle sin/cos of rotation at +20, and copies scale at +32. This confirms radian TRS for kinds 1/2/3. Other kinds do not call this helper; identity preview groups remain appropriate as an initial representation.

Kind 6 reads four signed words at +44: two descendant target names (-1 means absent), a parameter-table index, and a handler index. 0x240290 clears target-one flags 0x300 and sets target-two flags 0x300, then registers distinct callbacks. These are initial primary/secondary states, not a recovered complete destruction simulation. The parser now exposes state_control while preserving raw words. Export visibility is unchanged pending validation of descendant matching and the flag consumers.

0x240320 uses parameter index to read table 0x4858A0 into two runtime fields. 0x2403C0 stores handler index; loader optionally invokes a handler registry entry. Names such as hit points are deliberately not assigned yet.

These findings come from original-loader pseudocode; a dedicated instruction oracle has not yet been added. Next: validate state target lookup and visibility flag consumption, then export initial-state visibility without guessing destruction events.

## State target resolution

0x1B9F70 checks the starting object name, then searches child subtrees through 0x19E2F0. The latter visits self, then each child subtree in sibling order: first depth-first match wins. The parser now exposes primary_node/secondary_node and all authored matches. Runtime construction creates two objects for kind 3, so an authored node index is not necessarily a unique runtime object pointer.

Use `python arika_stages.py controls-json extracted/stg/s01/s01a.stg controls.json`. Missing named targets are reported as null rather than selected from another root or sibling. Initial visibility export remains unchanged. Callback 0x2409F0 re-applies the primary-enabled/secondary-hidden masks on event 0x08000000; event 0x20 toggles collision flag 16 through 0x1ABD30/0x1ABD70. Full flag consumers and destruction transitions still require tracing.
