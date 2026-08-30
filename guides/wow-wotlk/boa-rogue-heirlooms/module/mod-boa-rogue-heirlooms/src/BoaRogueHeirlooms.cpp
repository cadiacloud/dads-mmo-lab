/*
 * Copyright (C) 2016+ AzerothCore <www.azerothcore.org>, released under
 * GNU AGPL v3 license.
 */

#include "ConfigValueCache.h"
#include "DBCStores.h"
#include "ItemTemplate.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

namespace
{
enum class BoaConfigKey
{
    Enabled,
    NumConfigs
};

class BoaConfigData : public ConfigValueCache<BoaConfigKey>
{
public:
    BoaConfigData() : ConfigValueCache(BoaConfigKey::NumConfigs) { }

    void BuildConfigCache() override
    {
        SetConfigValue<bool>(BoaConfigKey::Enabled, "BoaRogueHeirlooms.Enable", true);
    }
};

BoaConfigData boaConfig;

constexpr uint32 FirstEntry = 900100;
constexpr uint32 LastEntry = 900116;
constexpr uint8 EndpointLevel = 80;
constexpr uint8 WarglaiveBreakpointLevel = 70;

struct StatEndpoint
{
    uint32 type;
    int32 valueAt80;
};

struct ItemEndpoint
{
    uint32 entry;
    uint32 statMask;
    std::array<StatEndpoint, 5> stats;
    uint8 statCount;
};

constexpr StatEndpoint EmptyStat{0, 0};

constexpr std::array<ItemEndpoint, 17> Endpoints = {{
    {900100, 4, {{{38, 95}, {3, 84}, {7, 84}, {32, 56}, {36, 48}}}, 5},
    {900101, 4, {{{38, 88}, {3, 78}, {7, 78}, {32, 52}, {44, 44}}}, 5},
    {900102, 8, {{{38, 228}, {3, 167}, {7, 183}, {31, 114}, {37, 106}}}, 5},
    {900103, 1, {{{38, 165}, {3, 128}, {7, 136}, {44, 90}, {36, 74}}}, 5},
    {900104, 8, {{{38, 196}, {3, 183}, {7, 183}, {32, 114}, {44, 106}}}, 5},
    {900105, 8, {{{38, 228}, {3, 167}, {7, 183}, {32, 122}, {31, 98}}}, 5},
    {900106, 1, {{{38, 165}, {3, 136}, {7, 136}, {32, 90}, {31, 82}}}, 5},
    {900107, 1, {{{38, 120}, {3, 102}, {7, 102}, {32, 60}, {44, 68}}}, 5},
    {900108, 1, {{{38, 181}, {3, 120}, {7, 136}, {32, 90}, {44, 74}}}, 5},
    {900109, 1, {{{38, 181}, {3, 120}, {7, 136}, {32, 90}, {44, 74}}}, 5},
    {900110, 0x40000, {{{38, 120}, {3, 102}, {7, 102}, {44, 68}, {36, 60}}}, 5},
    {900111, 0x40000, {{{38, 114}, {3, 97}, {7, 97}, {32, 65}, {44, 57}}}, 5},
    {900112, 0x40000, {{{38, 145}, {3, 109}, {7, 109}, {32, 73}, {31, 57}}}, 5},
    {900113, 0x40000, {{{38, 135}, {3, 88}, {7, 84}, {32, 59}, {31, 59}}}, 5},
    {900114, 2, {{{44, 184}, EmptyStat, EmptyStat, EmptyStat, EmptyStat}}, 1},
    {900115, 2, {{{44, 167}, EmptyStat, EmptyStat, EmptyStat, EmptyStat}}, 1},
    {900116, 16, {{{38, 66}, {3, 62}, {7, 62}, {32, 41}, {44, 33}}}, 5},
}};

struct WarglaiveLevel70Stats
{
    std::array<StatEndpoint, 5> stats;
};

constexpr WarglaiveLevel70Stats MainHandLevel70{{{
    {38, 0}, {3, 22}, {7, 29}, {31, 21}, {36, 0}
}}};
constexpr WarglaiveLevel70Stats OffHandLevel70{{{
    {38, 0}, {3, 21}, {7, 28}, {32, 23}, {44, 0}
}}};

bool IsEnabled()
{
    return boaConfig.GetConfigValue<bool>(BoaConfigKey::Enabled);
}

ItemEndpoint const* FindEndpoint(uint32 entry)
{
    if (entry < FirstEntry || entry > LastEntry)
        return nullptr;

    auto const itr = std::find_if(
        Endpoints.begin(),
        Endpoints.end(),
        [entry](ItemEndpoint const& endpoint) { return endpoint.entry == entry; });
    return itr == Endpoints.end() ? nullptr : &*itr;
}

int32 Interpolate(int32 from, int32 to, uint8 level, uint8 fromLevel, uint8 toLevel)
{
    if (level <= fromLevel)
        return from;
    if (level >= toLevel)
        return to;

    double const progress =
        static_cast<double>(level - fromLevel) / static_cast<double>(toLevel - fromLevel);
    return static_cast<int32>(std::lround(from + (to - from) * progress));
}

int32 ScaleUsingBlizzardCurve(int32 endpoint, uint8 level, uint32 statMask)
{
    ScalingStatValuesEntry const* current = sScalingStatValuesStore.LookupEntry(level);
    ScalingStatValuesEntry const* level80 = sScalingStatValuesStore.LookupEntry(EndpointLevel);
    if (!current || !level80)
        return 0;

    uint32 const currentMultiplier = current->getssdMultiplier(statMask);
    uint32 const endpointMultiplier = level80->getssdMultiplier(statMask);
    if (!endpointMultiplier)
        return 0;

    return static_cast<int32>(std::lround(
        static_cast<double>(endpoint) * currentMultiplier / endpointMultiplier));
}

int32 ScaleWarglaiveStat(
    uint32 entry,
    uint8 statIndex,
    uint8 level,
    StatEndpoint const& endpoint,
    uint32& statType)
{
    WarglaiveLevel70Stats const& breakpoint =
        entry == 900100 ? MainHandLevel70 : OffHandLevel70;
    StatEndpoint const& at70 = breakpoint.stats[statIndex];

    if (level <= WarglaiveBreakpointLevel)
    {
        statType = at70.type;
        ScalingStatValuesEntry const* current = sScalingStatValuesStore.LookupEntry(level);
        ScalingStatValuesEntry const* level70 =
            sScalingStatValuesStore.LookupEntry(WarglaiveBreakpointLevel);
        if (!current || !level70 || !level70->getssdMultiplier(4))
            return 0;

        return static_cast<int32>(std::lround(
            static_cast<double>(at70.valueAt80) * current->getssdMultiplier(4) /
            level70->getssdMultiplier(4)));
    }

    statType = endpoint.type;
    return Interpolate(
        at70.valueAt80,
        endpoint.valueAt80,
        level,
        WarglaiveBreakpointLevel,
        EndpointLevel);
}

void SetWeaponDamageForLevel(
    uint8 level,
    float level70Minimum,
    float level70Maximum,
    float level80Minimum,
    float level80Maximum,
    float& minimum,
    float& maximum)
{
    if (level <= WarglaiveBreakpointLevel)
    {
        ScalingStatValuesEntry const* current = sScalingStatValuesStore.LookupEntry(level);
        ScalingStatValuesEntry const* level70 =
            sScalingStatValuesStore.LookupEntry(WarglaiveBreakpointLevel);
        if (!current || !level70 || !level70->getDPSMod(0x200))
            return;

        double const ratio = static_cast<double>(current->getDPSMod(0x200)) /
            level70->getDPSMod(0x200);
        minimum = static_cast<float>(level70Minimum * ratio);
        maximum = static_cast<float>(level70Maximum * ratio);
        return;
    }

    double const progress = static_cast<double>(level - WarglaiveBreakpointLevel) /
        (EndpointLevel - WarglaiveBreakpointLevel);
    minimum = static_cast<float>(level70Minimum + (level80Minimum - level70Minimum) * progress);
    maximum = static_cast<float>(level70Maximum + (level80Maximum - level70Maximum) * progress);
}

class BoaRogueHeirloomWorldScript : public WorldScript
{
public:
    BoaRogueHeirloomWorldScript() : WorldScript(
        "BoaRogueHeirloomWorldScript",
        {WORLDHOOK_ON_BEFORE_CONFIG_LOAD, WORLDHOOK_ON_STARTUP})
    {
    }

    void OnBeforeConfigLoad(bool reload) override
    {
        boaConfig.Initialize(reload);
    }

    void OnStartup() override
    {
        LOG_INFO(
            "module.boa-rogue-heirlooms",
            "BOA rogue heroic endpoint scaling is {}",
            IsEnabled() ? "enabled" : "disabled");
    }
};

class BoaRogueHeirloomPlayerScript : public PlayerScript
{
public:
    BoaRogueHeirloomPlayerScript() : PlayerScript(
        "BoaRogueHeirloomPlayerScript",
        {PLAYERHOOK_ON_CUSTOM_SCALING_STAT_VALUE, PLAYERHOOK_ON_APPLY_WEAPON_DAMAGE})
    {
    }

    void OnPlayerCustomScalingStatValue(
        Player* player,
        ItemTemplate const* proto,
        uint32& statType,
        int32& value,
        uint8 statIndex,
        uint32 /*scalingStatValue*/,
        ScalingStatValuesEntry const* /*scalingValues*/) override
    {
        if (!IsEnabled() || !player || !proto)
            return;

        ItemEndpoint const* endpoint = FindEndpoint(proto->ItemId);
        if (!endpoint || statIndex >= endpoint->statCount)
            return;

        StatEndpoint const& stat = endpoint->stats[statIndex];
        if (proto->ItemId == 900100 || proto->ItemId == 900101)
        {
            value = ScaleWarglaiveStat(
                proto->ItemId,
                statIndex,
                std::min<uint8>(player->GetLevel(), EndpointLevel),
                stat,
                statType);
            return;
        }

        statType = stat.type;
        value = ScaleUsingBlizzardCurve(
            stat.valueAt80,
            std::min<uint8>(player->GetLevel(), EndpointLevel),
            endpoint->statMask);
    }

    void OnPlayerApplyWeaponDamage(
        Player* player,
        uint8 /*slot*/,
        ItemTemplate const* proto,
        float& minimum,
        float& maximum,
        uint8 damageIndex) override
    {
        if (!IsEnabled() || !player || !proto || damageIndex != 0)
            return;

        uint8 const level = std::min<uint8>(player->GetLevel(), EndpointLevel);
        switch (proto->ItemId)
        {
            case 900100:
                SetWeaponDamageForLevel(level, 214.0f, 398.0f, 518.0f, 964.0f, minimum, maximum);
                break;
            case 900101:
                SetWeaponDamageForLevel(level, 107.0f, 199.0f, 245.0f, 456.0f, minimum, maximum);
                break;
            case 900116:
            {
                ScalingStatValuesEntry const* current = sScalingStatValuesStore.LookupEntry(level);
                ScalingStatValuesEntry const* level80 = sScalingStatValuesStore.LookupEntry(EndpointLevel);
                if (!current || !level80 || !level80->getDPSMod(0x2000))
                    break;
                double const ratio = static_cast<double>(current->getDPSMod(0x2000)) /
                    level80->getDPSMod(0x2000);
                minimum = static_cast<float>(783.0 * ratio);
                maximum = static_cast<float>(1071.0 * ratio);
                break;
            }
            default:
                break;
        }
    }
};
}

void Addmod_boa_rogue_heirloomsScripts()
{
    new BoaRogueHeirloomWorldScript();
    new BoaRogueHeirloomPlayerScript();
}
