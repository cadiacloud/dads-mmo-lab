/*
 * Copyright (C) 2016+ AzerothCore <www.azerothcore.org>, released under
 * GNU AGPL v3 license.
 */

#include "AreaDefines.h"
#include "Bag.h"
#include "Chat.h"
#include "ConfigValueCache.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellInfo.h"
#include "WorldSession.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <mutex>
#include <shared_mutex>
#include <unordered_map>

namespace
{
constexpr uint8 StockDeathKnightLevel = 55;

enum class NoviceConfigKey
{
    Enabled,
    ScaleSpellDamage,
    MinimumDamageScale,
    Announce,
    AllowInternalSessions,
    NumConfigs
};

class NoviceConfigData : public ConfigValueCache<NoviceConfigKey>
{
public:
    NoviceConfigData() : ConfigValueCache(NoviceConfigKey::NumConfigs) { }

    void BuildConfigCache() override
    {
        SetConfigValue<bool>(NoviceConfigKey::Enabled, "NoviceDeathKnight.Enable", false);
        SetConfigValue<bool>(NoviceConfigKey::ScaleSpellDamage, "NoviceDeathKnight.ScaleSpellDamage", true);
        SetConfigValue<float>(
            NoviceConfigKey::MinimumDamageScale,
            "NoviceDeathKnight.MinimumDamageScale",
            0.10f,
            ConfigValueCache::Reloadable::Yes,
            [](float const& value) { return value >= 0.01f && value <= 1.0f; },
            ">= 0.01 and <= 1.0");
        SetConfigValue<bool>(NoviceConfigKey::Announce, "NoviceDeathKnight.Announce", true);
        SetConfigValue<bool>(
            NoviceConfigKey::AllowInternalSessions,
            "NoviceDeathKnight.AllowInternalSessions",
            false);
    }
};

NoviceConfigData noviceConfig;
std::shared_mutex noviceCharactersMutex;
std::unordered_map<uint32, bool> noviceCharacters;

struct AbilityUnlock
{
    uint32 spellId;
    uint8 level;
};

std::array<AbilityUnlock, 55> const ManagedAbilities = {{
    { 45477, 1 },  // Icy Touch (Rank 1)
    { 45462, 1 },  // Plague Strike (Rank 1)
    { 45902, 2 },  // Blood Strike (Rank 1)
    { 47541, 4 },  // Death Coil (Rank 1)
    { 49576, 6 },  // Death Grip
    { 48266, 8 },  // Blood Presence
    { 56222, 10 }, // Dark Command
    { 50842, 12 }, // Pestilence
    { 47528, 14 }, // Mind Freeze
    { 45524, 16 }, // Chains of Ice
    { 49998, 18 }, // Death Strike (Rank 1)
    { 48263, 20 }, // Frost Presence
    { 46584, 22 }, // Raise Dead
    { 48721, 24 }, // Blood Boil (Rank 1)
    { 47476, 26 }, // Strangulate
    { 43265, 28 }, // Death and Decay (Rank 1)
    { 3714, 30 },  // Path of Frost
    { 48792, 32 }, // Icebound Fortitude
    { 49020, 34 }, // Obliterate (Rank 1)
    { 45529, 36 }, // Blood Tap
    { 57330, 38 }, // Horn of Winter (Rank 1)
    { 48743, 40 }, // Death Pact
    { 56815, 42 }, // Rune Strike
    { 48707, 44 }, // Anti-Magic Shell
    { 48265, 46 }, // Unholy Presence
    { 61999, 48 }, // Raise Ally
    { 47568, 50 }, // Empower Rune Weapon
    { 42650, 54 }, // Army of the Dead
    { 53428, 55 }, // Runeforging
    { 50977, 55 }, // Death Gate
    { 48778, 55 }, // Acherus Deathcharger
    { 49926, 59 }, // Blood Strike (Rank 2)
    { 49917, 60 }, // Plague Strike (Rank 2)
    { 49896, 61 }, // Icy Touch (Rank 2)
    { 49892, 62 }, // Death Coil (Rank 2)
    { 49999, 63 }, // Death Strike (Rank 2)
    { 49927, 64 }, // Blood Strike (Rank 3)
    { 49918, 65 }, // Plague Strike (Rank 3)
    { 49939, 66 }, // Blood Boil (Rank 2)
    { 49903, 67 }, // Icy Touch (Rank 3)
    { 49936, 67 }, // Death and Decay (Rank 2)
    { 51423, 67 }, // Obliterate (Rank 2)
    { 49893, 68 }, // Death Coil (Rank 3)
    { 49928, 69 }, // Blood Strike (Rank 4)
    { 45463, 70 }, // Death Strike (Rank 3)
    { 49919, 70 }, // Plague Strike (Rank 4)
    { 49940, 72 }, // Blood Boil (Rank 3)
    { 49904, 73 }, // Icy Touch (Rank 4)
    { 49937, 73 }, // Death and Decay (Rank 3)
    { 51424, 73 }, // Obliterate (Rank 3)
    { 49929, 74 }, // Blood Strike (Rank 5)
    { 49920, 75 }, // Plague Strike (Rank 5)
    { 49923, 75 }, // Death Strike (Rank 4)
    { 57623, 75 }, // Horn of Winter (Rank 2)
}};

std::array<AbilityUnlock, 9> const FinalTrainedRanks = {{
    { 49894, 76 }, // Death Coil (Rank 4)
    { 49909, 78 }, // Icy Touch (Rank 5)
    { 49941, 78 }, // Blood Boil (Rank 4)
    { 51425, 79 }, // Obliterate (Rank 4)
    { 49895, 80 }, // Death Coil (Rank 5)
    { 49921, 80 }, // Plague Strike (Rank 6)
    { 49924, 80 }, // Death Strike (Rank 5)
    { 49930, 80 }, // Blood Strike (Rank 6)
    { 49938, 80 }, // Death and Decay (Rank 4)
}};

std::array<AbilityUnlock, 4> const TalentGatedRanks = {{
    { 51328, 80 }, // Corpse Explosion is talent-gated; retained only if already known
    { 51411, 80 }, // Howling Blast is talent-gated; retained only if already known
    { 55262, 80 }, // Heart Strike is talent-gated; retained only if already known
    { 55268, 80 }, // Frost Strike is talent-gated; retained only if already known
}};

struct ActionBarUnlock
{
    uint8 button;
    uint32 spellId;
    uint8 level;
};

std::array<ActionBarUnlock, 5> const ActionBarAbilities = {{
    { 0, 45477, 1 },
    { 1, 45462, 1 },
    { 2, 45902, 2 },
    { 3, 47541, 4 },
    { 4, 49576, 6 },
}};

std::array<uint32, 8> const StarterItems = {{
    3273,  // Rugged Mail Vest
    2172,  // Rustic Belt
    4917,  // Battleworn Chain Leggings
    2691,  // Outfitter Boots
    11849, // Rustmetal Bracers
    2547,  // Boar Handler Gloves
    49778, // Worn Greatsword
    6948,  // Hearthstone
}};

bool IsEnabled()
{
    return noviceConfig.GetConfigValue<bool>(NoviceConfigKey::Enabled);
}

void LoadNoviceCharacters()
{
    std::unordered_map<uint32, bool> loadedCharacters;
    QueryResult result = CharacterDatabase.Query(
        "SELECT character_guid, initialized FROM novice_death_knight_characters WHERE active = 1");

    if (result)
    {
        do
        {
            Field* fields = result->Fetch();
            loadedCharacters.emplace(fields[0].Get<uint32>(), fields[1].Get<bool>());
        } while (result->NextRow());
    }

    std::unique_lock lock(noviceCharactersMutex);
    noviceCharacters = std::move(loadedCharacters);
    LOG_INFO("module.novice-dk", "Loaded {} enrolled novice Death Knights", noviceCharacters.size());
}

bool IsNoviceGuid(uint32 guid)
{
    std::shared_lock lock(noviceCharactersMutex);
    return noviceCharacters.contains(guid);
}

bool IsNoviceCharacter(Player const* player)
{
    return player && player->getClass() == CLASS_DEATH_KNIGHT &&
        IsNoviceGuid(player->GetGUID().GetCounter());
}

bool NeedsInitialization(uint32 guid)
{
    std::shared_lock lock(noviceCharactersMutex);
    auto const itr = noviceCharacters.find(guid);
    return itr != noviceCharacters.end() && !itr->second;
}

void RegisterNovice(uint32 guid)
{
    CharacterDatabase.DirectExecute(
        "INSERT INTO novice_death_knight_characters (character_guid, initialized, active) "
        "VALUES ({}, 0, 1) ON DUPLICATE KEY UPDATE initialized = 0, active = 1",
        guid);

    std::unique_lock lock(noviceCharactersMutex);
    noviceCharacters[guid] = false;
}

void UnregisterNovice(uint32 guid)
{
    std::unique_lock lock(noviceCharactersMutex);
    noviceCharacters.erase(guid);
}

template <std::size_t Size>
void SynchronizeAbilityList(Player* player, std::array<AbilityUnlock, Size> const& abilities)
{
    uint8 const level = player->GetLevel();
    for (AbilityUnlock const& ability : abilities)
    {
        if (level >= ability.level)
        {
            if (!player->HasSpell(ability.spellId))
                player->learnSpell(ability.spellId, false);
        }
        else if (player->HasSpell(ability.spellId))
            player->removeSpell(ability.spellId, SPEC_MASK_ALL, false);
    }
}

void SynchronizeAbilities(Player* player)
{
    SynchronizeAbilityList(player, ManagedAbilities);
    SynchronizeAbilityList(player, FinalTrainedRanks);

    // These final ranks depend on talent-granted base abilities. Never grant
    // the talent spell itself; only preserve a rank that the player already
    // legitimately knows.
    for (AbilityUnlock const& ability : TalentGatedRanks)
    {
        if (player->GetLevel() < ability.level && player->HasSpell(ability.spellId))
            player->removeSpell(ability.spellId, SPEC_MASK_ALL, false);
    }
}

void ConfigureInitialActionBar(Player* player)
{
    for (uint8 button = 0; button < 5; ++button)
        player->removeActionButton(button);

    for (ActionBarUnlock const& ability : ActionBarAbilities)
    {
        if (player->GetLevel() >= ability.level)
            player->addActionButton(ability.button, ability.spellId, ACTION_BUTTON_SPELL);
    }
}

void AddNewActionBarAbilities(Player* player, uint8 oldLevel)
{
    for (ActionBarUnlock const& ability : ActionBarAbilities)
    {
        if (oldLevel < ability.level && player->GetLevel() >= ability.level &&
            !player->GetActionButton(ability.button))
        {
            player->addActionButton(ability.button, ability.spellId, ACTION_BUTTON_SPELL);
        }
    }
}

void DestroyCreationInventory(Player* player)
{
    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
    {
        Bag* bag = player->GetBagByPos(bagSlot);
        if (!bag)
            continue;

        for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
        {
            if (bag->GetItemByPos(slot))
                player->DestroyItem(bagSlot, slot, true);
        }
    }

    for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
    {
        if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
            player->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);
    }

    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
    {
        if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
            player->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);
    }

    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
    {
        if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, bagSlot))
            player->DestroyItem(INVENTORY_SLOT_BAG_0, bagSlot, true);
    }
}

void GiveStarterItems(Player* player)
{
    for (uint32 itemId : StarterItems)
    {
        if (!player->StoreNewItemInBestSlots(itemId, 1))
        {
            LOG_ERROR(
                "module.novice-dk",
                "Could not give starter item {} to {}",
                itemId,
                player->GetGUID().ToString());
        }
    }
}

bool InitializeNovice(Player* player)
{
    if (!player || player->getClass() != CLASS_DEATH_KNIGHT)
        return false;

    DestroyCreationInventory(player);
    player->GiveLevel(1);
    player->SetMoney(0);
    player->SetSkill(SKILL_FIRST_AID, 0, 0, 0);
    player->SetSkill(SKILL_RIDING, 0, 0, 0);
    SynchronizeAbilities(player);
    ConfigureInitialActionBar(player);
    GiveStarterItems(player);
    player->SetFullHealth();

    CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
    player->SaveToDB(transaction, false, false);
    transaction->Append(
        "UPDATE novice_death_knight_characters SET initialized = 1 WHERE character_guid = {}",
        player->GetGUID().GetCounter());
    CharacterDatabase.CommitTransaction(transaction);

    {
        std::unique_lock lock(noviceCharactersMutex);
        noviceCharacters[player->GetGUID().GetCounter()] = true;
    }

    LOG_INFO(
        "module.novice-dk",
        "Initialized novice Death Knight {} at level 1",
        player->GetGUID().ToString());
    return true;
}

PlayerInfo const* GetRacialStartInfo(Player const* player)
{
    std::array<uint8, 10> const fallbackClasses = {{
        CLASS_WARRIOR,
        CLASS_PALADIN,
        CLASS_ROGUE,
        CLASS_HUNTER,
        CLASS_PRIEST,
        CLASS_SHAMAN,
        CLASS_MAGE,
        CLASS_WARLOCK,
        CLASS_DRUID,
        CLASS_DEATH_KNIGHT,
    }};

    for (uint8 playerClass : fallbackClasses)
    {
        if (PlayerInfo const* info = sObjectMgr->GetPlayerInfo(player->getRace(), playerClass))
        {
            if (playerClass != CLASS_DEATH_KNIGHT)
                return info;
        }
    }

    return nullptr;
}

bool MoveToRacialStart(Player* player)
{
    PlayerInfo const* startInfo = GetRacialStartInfo(player);
    if (!startInfo)
    {
        LOG_ERROR(
            "module.novice-dk",
            "No racial starting location found for {}",
            player->GetGUID().ToString());
        return false;
    }

    WorldLocation const startLocation(
        startInfo->mapId,
        startInfo->positionX,
        startInfo->positionY,
        startInfo->positionZ,
        startInfo->orientation);
    player->SetHomebind(startLocation, startInfo->areaId);

    bool const alreadyKnewDeathGate = player->HasSpell(50977);
    if (!alreadyKnewDeathGate)
        player->learnSpell(50977, false);

    bool const teleported = player->TeleportTo(startLocation);
    if (teleported && !alreadyKnewDeathGate && player->GetLevel() < StockDeathKnightLevel)
        player->removeSpell(50977, SPEC_MASK_ALL, false);

    if (!teleported)
    {
        LOG_ERROR(
            "module.novice-dk",
            "Could not move {} from Ebon Hold to the racial starting location",
            player->GetGUID().ToString());
    }

    return teleported;
}

float GetSpellDamageScale(Player const* player)
{
    float const levelScale = static_cast<float>(player->GetLevel()) / StockDeathKnightLevel;
    float const minimumScale = noviceConfig.GetConfigValue<float>(NoviceConfigKey::MinimumDamageScale);
    return std::clamp(std::max(levelScale, minimumScale), 0.01f, 1.0f);
}

bool ShouldScaleSpellDamage(Unit* attacker, SpellInfo const* spellInfo)
{
    if (!IsEnabled() ||
        !noviceConfig.GetConfigValue<bool>(NoviceConfigKey::ScaleSpellDamage) ||
        !attacker ||
        !spellInfo ||
        spellInfo->SpellFamilyName != SPELLFAMILY_DEATHKNIGHT)
    {
        return false;
    }

    Player* player = attacker->ToPlayer();
    return player && player->GetLevel() < StockDeathKnightLevel && IsNoviceCharacter(player);
}

class NoviceDeathKnightWorldScript : public WorldScript
{
public:
    NoviceDeathKnightWorldScript() : WorldScript(
        "NoviceDeathKnightWorldScript",
        { WORLDHOOK_ON_BEFORE_CONFIG_LOAD, WORLDHOOK_ON_STARTUP })
    {
    }

    void OnBeforeConfigLoad(bool reload) override
    {
        noviceConfig.Initialize(reload);
    }

    void OnStartup() override
    {
        LoadNoviceCharacters();
        LOG_INFO(
            "module.novice-dk",
            "Novice Death Knight module is {}",
            IsEnabled() ? "enabled" : "disabled");
    }
};

class NoviceDeathKnightPlayerScript : public PlayerScript
{
public:
    NoviceDeathKnightPlayerScript() : PlayerScript(
        "NoviceDeathKnightPlayerScript",
        {
            PLAYERHOOK_ON_CALCULATE_TALENTS_POINTS,
            PLAYERHOOK_ON_LEVEL_CHANGED,
            PLAYERHOOK_ON_LOGIN,
            PLAYERHOOK_ON_CREATE,
            PLAYERHOOK_ON_DELETE,
            PLAYERHOOK_ON_FIRST_LOGIN,
        })
    {
    }

    void OnPlayerCreate(Player* player) override
    {
        if (!IsEnabled() || player->getClass() != CLASS_DEATH_KNIGHT)
            return;

        bool const allowInternal =
            noviceConfig.GetConfigValue<bool>(NoviceConfigKey::AllowInternalSessions);
        if (!allowInternal &&
            (!player->GetSession() || player->GetSession()->GetRemoteAddress().empty()))
        {
            return;
        }

        uint32 const guid = player->GetGUID().GetCounter();
        RegisterNovice(guid);
        InitializeNovice(player);
    }

    void OnPlayerLogin(Player* player) override
    {
        if (!IsEnabled() || !IsNoviceCharacter(player))
            return;

        uint32 const guid = player->GetGUID().GetCounter();
        if (NeedsInitialization(guid))
            InitializeNovice(player);

        SynchronizeAbilities(player);
        if (player->GetLevel() < StockDeathKnightLevel && player->GetMapId() == MAP_EBON_HOLD)
            MoveToRacialStart(player);
    }

    void OnPlayerFirstLogin(Player* player) override
    {
        if (!IsEnabled() ||
            !IsNoviceCharacter(player) ||
            !noviceConfig.GetConfigValue<bool>(NoviceConfigKey::Announce) ||
            !player->GetSession())
        {
            return;
        }

        ChatHandler(player->GetSession()).SendSysMessage(
            "Novice Death Knight progression is active. Core abilities and ranks unlock as you level; "
            "talent points begin at level 10.");
    }

    void OnPlayerLevelChanged(Player* player, uint8 oldLevel) override
    {
        if (!IsEnabled() || !IsNoviceCharacter(player))
            return;

        SynchronizeAbilities(player);
        AddNewActionBarAbilities(player, oldLevel);
    }

    void OnPlayerCalculateTalentsPoints(Player const* player, uint32& talentPointsForLevel) override
    {
        if (!IsEnabled() || !IsNoviceCharacter(player))
            return;

        talentPointsForLevel = player->GetLevel() < 10 ? 0 : player->GetLevel() - 9;
    }

    void OnPlayerDelete(ObjectGuid guid, uint32 /*accountId*/) override
    {
        UnregisterNovice(guid.GetCounter());
    }
};

class NoviceDeathKnightUnitScript : public UnitScript
{
public:
    NoviceDeathKnightUnitScript() : UnitScript(
        "NoviceDeathKnightUnitScript",
        true,
        { UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK, UNITHOOK_MODIFY_SPELL_DAMAGE_TAKEN })
    {
    }

    void ModifySpellDamageTaken(
        Unit* /*target*/,
        Unit* attacker,
        int32& damage,
        SpellInfo const* spellInfo) override
    {
        if (damage <= 0 ||
            !ShouldScaleSpellDamage(attacker, spellInfo) ||
            spellInfo->DmgClass == SPELL_DAMAGE_CLASS_MELEE)
        {
            return;
        }

        damage = static_cast<int32>(std::lround(damage * GetSpellDamageScale(attacker->ToPlayer())));
    }

    void ModifyPeriodicDamageAurasTick(
        Unit* /*target*/,
        Unit* attacker,
        uint32& damage,
        SpellInfo const* spellInfo) override
    {
        if (!damage || !ShouldScaleSpellDamage(attacker, spellInfo))
            return;

        damage = static_cast<uint32>(std::lround(damage * GetSpellDamageScale(attacker->ToPlayer())));
    }
};
}

void Addmod_novice_death_knightScripts()
{
    new NoviceDeathKnightWorldScript();
    new NoviceDeathKnightPlayerScript();
    new NoviceDeathKnightUnitScript();
}
