#ifndef ARIKA_MENU_LOGIC_H
#define ARIKA_MENU_LOGIC_H

// Partial behavioral reconstruction for the researched SLES_541.61 build.
// No rendering, audio, app lifecycle or animation/input gating is implemented.
// Slot indices are confirmed; retail menu labels and physical keys are not.
struct s_menu_route
{
    bool valid;
    int mode_selector; // -1 means leave the selector unchanged.
    int next_app_id;
};

class c_main_menu_logic
{
public:
    c_main_menu_logic() : m_selected(0), m_previous(-1)
    {
    }

    bool set_selected(int index)
    {
        if (index < 0 || index >= 7)
        {
            return false;
        }
        m_previous = m_selected;
        m_selected = index;
        return true;
    }

    int get_selected() const
    {
        return m_selected;
    }

    int get_previous() const
    {
        return m_previous;
    }

    // sub_3751F0 records the prior selection before the item entry callback.
    // sub_3758F0 / sub_37A300 derive their neighbor flags from that index.
    int get_neighbor(int direction) const
    {
        return get_neighbor(direction, m_previous == 2,
            m_previous == 0 || m_previous == 1 || m_previous == 5);
    }

    bool move(int direction)
    {
        return set_selected(get_neighbor(direction));
    }

    // sub_375270 dispatches slots +0x34/+0x38/+0x3C/+0x40.
    // Dynamic conditions are the original item-local byte flags, not unlocks.
    int get_neighbor(int direction, bool item_0_flag, bool item_2_flag) const
    {
        if (direction < 0 || direction >= 4)
        {
            return -1;
        }
        const int neighbors[7][4] =
        {
            { 3, -1, -1, 1 },
            { 2, -1, 0, 4 },
            { 6, 4, 0, -1 },
            { -1, 0, -1, 5 },
            { 2, -1, 1, -1 },
            { -1, 2, 3, 6 },
            { -1, 2, 5, -1 }
        };
        if (m_selected == 0 && direction == 3)
        {
            return item_0_flag ? 2 : 1;
        }
        if (m_selected == 2 && direction == 0)
        {
            return item_2_flag ? 5 : 6;
        }
        if (m_selected == 2 && direction == 1)
        {
            return item_2_flag ? 1 : 4;
        }
        return neighbors[m_selected][direction];
    }

    bool move(int direction, bool item_0_flag, bool item_2_flag)
    {
        int next = get_neighbor(direction, item_0_flag, item_2_flag);
        if (next < 0)
        {
            return false;
        }
        return set_selected(next);
    }

    // Routing portion of sub_3FE020, after its transition wait completes.
    s_menu_route get_route(bool cancelled) const
    {
        s_menu_route result = { true, -1, 3 };
        if (cancelled)
        {
            return result;
        }
        const int selectors[7] = { 1, 2, 3, 5, 4, 6, 7 };
        const int app_ids[7] = { 10, 10, 10, 44, 10, 45, 46 };
        result.mode_selector = selectors[m_selected];
        result.next_app_id = app_ids[m_selected];
        return result;
    }

private:
    int m_selected;
    int m_previous;
};

#endif
