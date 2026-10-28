#ifndef ARIKA_MENU_RNG_H
#define ARIKA_MENU_RNG_H

#include <stdint.h>

// Native algorithm only. Supply a captured or deliberately authored context state.
class c_menu_rng
{
public:
    explicit c_menu_rng(uint64_t state) : m_state(state)
    {
    }

    uint64_t get_state() const
    {
        return m_state;
    }

    uint32_t next()
    {
        const uint64_t multiplier =
            (static_cast<uint64_t>(0x5851F42Du) << 32) | 0x4C957F2Du;
        m_state = m_state * multiplier + 1;
        return static_cast<uint32_t>((m_state >> 32) & 0x7FFFFFFFu);
    }

private:
    uint64_t m_state;
};

#endif
