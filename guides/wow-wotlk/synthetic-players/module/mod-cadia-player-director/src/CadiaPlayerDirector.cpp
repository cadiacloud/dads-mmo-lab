/*
 * Copyright (C) 2016+ AzerothCore <www.azerothcore.org>, released under
 * GNU AGPL v3 license.
 */

#include "AuctionHouseMgr.h"
#include "Bag.h"
#include "CellImpl.h"
#include "CharacterCache.h"
#include "ChooseTravelTargetAction.h"
#include "ConfigValueCache.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Event.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Group.h"
#include "Guild.h"
#include "GuildMgr.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Item.h"
#include "ItemUsageValue.h"
#include "Log.h"
#include "Mail.h"
#include "NearestGameObjects.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "PlayerbotAI.h"
#include "PlayerbotFactory.h"
#include "PlayerbotMgr.h"
#include "PlayerbotSecurity.h"
#include "Playerbots.h"
#include "RandomPlayerbotMgr.h"
#include "RtiTargetValue.h"
#include "ScriptMgr.h"
#include "StringFormat.h"
#include "TravelMgr.h"
#include "Unit.h"
#include "World.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <deque>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>

namespace
{
enum class DirectorConfigKey
{
    Enabled,
    PollIntervalMs,
    SnapshotIntervalMs,
    BatchSize,
    VerificationTimeoutMs,
    EconomyIntervalMs,
    ProfessionIntervalMs,
    ProfessionAutoTrainRanks,
    ProfessionProvisionTools,
    ProfessionMaxGatheringSkills,
    ProfessionGrantTaxiNodes,
    NumConfigs
};

class DirectorConfigData : public ConfigValueCache<DirectorConfigKey>
{
public:
    DirectorConfigData() : ConfigValueCache(DirectorConfigKey::NumConfigs) { }

    void BuildConfigCache() override
    {
        SetConfigValue<bool>(DirectorConfigKey::Enabled, "CadiaPlayerDirector.Enable", true);
        SetConfigValue<uint32>(
            DirectorConfigKey::PollIntervalMs,
            "CadiaPlayerDirector.PollIntervalMs",
            250);
        SetConfigValue<uint32>(
            DirectorConfigKey::SnapshotIntervalMs,
            "CadiaPlayerDirector.SnapshotIntervalMs",
            1000);
        SetConfigValue<uint32>(DirectorConfigKey::BatchSize, "CadiaPlayerDirector.BatchSize", 10);
        SetConfigValue<uint32>(
            DirectorConfigKey::VerificationTimeoutMs,
            "CadiaPlayerDirector.VerificationTimeoutMs",
            15000);
        SetConfigValue<uint32>(
            DirectorConfigKey::EconomyIntervalMs,
            "CadiaPlayerDirector.EconomyIntervalMs",
            120000);
        SetConfigValue<uint32>(
            DirectorConfigKey::ProfessionIntervalMs,
            "CadiaPlayerDirector.ProfessionIntervalMs",
            5000);
        SetConfigValue<bool>(
            DirectorConfigKey::ProfessionAutoTrainRanks,
            "CadiaPlayerDirector.ProfessionAutoTrainRanks",
            true);
        SetConfigValue<bool>(
            DirectorConfigKey::ProfessionProvisionTools,
            "CadiaPlayerDirector.ProfessionProvisionTools",
            true);
        SetConfigValue<bool>(
            DirectorConfigKey::ProfessionMaxGatheringSkills,
            "CadiaPlayerDirector.ProfessionMaxGatheringSkills",
            true);
        SetConfigValue<bool>(
            DirectorConfigKey::ProfessionGrantTaxiNodes,
            "CadiaPlayerDirector.ProfessionGrantTaxiNodes",
            true);
    }
};

DirectorConfigData directorConfig;

enum class IntentStatus : uint8
{
    Pending = 0,
    Accepted = 1,
    Running = 2,
    Succeeded = 3,
    Failed = 4,
    Rejected = 5,
    Expired = 6,
    Preempted = 7
};

enum class IntentType
{
    Follow,
    HoldPosition,
    AttackPlayerTarget,
    PullPlayerTarget,
    Retreat,
    PrepareParty,
    PolymorphPlayerTarget,
    SapPlayerTarget,
    StunPlayerTarget,
    SlowFallIssuer,
    PowerUp,
    StartFarming,
    StopFarming,
    StartEconomy,
    StopEconomy,
    WorkAuctionHouse,
    CraftSupplies,
    CollectMail,
    DepositGuildBank,
    ShareGold,
    ReportToGroup,
    ContinueRoutine
};

enum class GroupDutyMode : uint8
{
    Routine = 0,
    AwaitingDecision = 1,
    Reporting = 2,
    RoutineWhileGrouped = 3
};

struct GroupDutyState
{
    GroupDutyMode mode = GroupDutyMode::Routine;
    uint64 groupGuid = 0;
    uint32 masterGuid = 0;
};

struct IntentRow
{
    uint64 id;
    uint32 issuerGuid;
    uint32 botGuid;
    std::string type;
    std::string parameters;
    bool expired;
    bool bindingValid;
    bool cadiaAuthority;
};

struct PendingVerification
{
    uint64 intentId;
    IntentType type;
    uint32 issuerGuid;
    uint32 botGuid;
    ObjectGuid targetGuid;
    std::chrono::steady_clock::time_point deadline;
};

struct EconomyProfile
{
    uint32 botGuid = 0;
    bool autoList = true;
    bool autoBuy = true;
    bool autoCraft = true;
    uint64 minimumReserve = 1000000;
    uint64 maxSpendPerCycle = 250000;
    uint64 maxGoldGift = 1000000;
    uint16 maxOwnedAuctions = 12;
};

struct EconomyResult
{
    std::string resultCode = "auction_no_work";
    std::string actionKind = "NONE";
    uint32 itemEntry = 0;
    uint32 itemCount = 0;
    int64 copperDelta = 0;
};

struct AuctionContext
{
    AuctionHouseId houseId;
    AuctionHouseEntry const* entry;
    AuctionHouseObject* house;
};

struct ProfessionObjective
{
    uint64 id = 0;
    uint64 planId = 0;
    uint32 botGuid = 0;
    uint16 skillId = 0;
    uint8 stageOrder = 0;
    uint16 skillFrom = 0;
    uint16 skillTo = 0;
    uint8 minCharacterLevel = 0;
    std::string profession;
    std::string selectedZone;
    uint32 selectedZoneId = 0;
    uint32 toolItemId = 0;
    std::string depositCategory;
    uint8 guildBankTab = 0;
    uint8 depositFreeSlots = 6;
};

struct MaterialKitTarget
{
    uint64 id = 0;
    uint64 planId = 0;
    uint32 botGuid = 0;
    uint16 gatheringSkillId = 0;
    uint32 itemEntry = 0;
    uint32 requiredCount = 0;
    uint32 bankThreshold = 0;
    uint32 observedBankCount = 0;
    uint32 guildId = 0;
    uint32 selectedZoneId = 0;
    uint8 minCharacterLevel = 1;
    uint8 guildBankTab = 0;
    std::string professionName;
    std::string itemName;
    std::string acquisitionMode;
    std::string depositCategory;
    std::string selectedZone;
};

enum class ProfessionDepositResult
{
    Deposited,
    NoMaterial,
    NoGuild,
    NoRights,
    BankFull
};

struct ProfessionRank
{
    uint16 skillId;
    uint16 requiredSkill;
    uint16 newCap;
    uint8 requiredLevel;
    uint32 spellId;
};

class ProfessionTravelDestination final : public TravelDestination
{
public:
    ProfessionTravelDestination(
        uint64 objectiveId,
        uint32 zoneId,
        uint16 requiredSkill,
        int32 entry,
        uint32 mapId,
        float x,
        float y,
        float z,
        std::string title)
        : TravelDestination(4.0f, 12.0f),
          _objectiveId(objectiveId),
          _zoneId(zoneId),
          _requiredSkill(requiredSkill),
          _entry(entry),
          _point(mapId, x, y, z),
          _title(std::move(title))
    {
        addPoint(&_point);
        setExpireDelay(20 * MINUTE * IN_MILLISECONDS);
        setCooldownDelay(1000);
    }

    bool isActive([[maybe_unused]] Player* bot) override { return true; }
    std::string const getName() override { return "ProfessionTravelDestination"; }
    int32 getEntry() override { return _entry; }
    std::string const getTitle() override { return _title; }
    uint64 GetObjectiveId() const { return _objectiveId; }
    uint32 GetZoneId() const { return _zoneId; }
    uint16 GetRequiredSkill() const { return _requiredSkill; }

private:
    uint64 _objectiveId;
    uint32 _zoneId;
    uint16 _requiredSkill;
    int32 _entry;
    WorldPosition _point;
    std::string _title;
};

std::array<ProfessionRank, 15> const ProfessionRanks = {{
    {SKILL_MINING, 50, 150, 10, 2576},
    {SKILL_MINING, 125, 225, 10, 3564},
    {SKILL_MINING, 200, 300, 25, 10248},
    {SKILL_MINING, 275, 375, 40, 29354},
    {SKILL_MINING, 350, 450, 55, 50310},
    {SKILL_HERBALISM, 50, 150, 10, 2368},
    {SKILL_HERBALISM, 125, 225, 10, 3570},
    {SKILL_HERBALISM, 200, 300, 25, 11993},
    {SKILL_HERBALISM, 275, 375, 40, 28695},
    {SKILL_HERBALISM, 350, 450, 55, 50300},
    {SKILL_SKINNING, 50, 150, 10, 8617},
    {SKILL_SKINNING, 125, 225, 10, 8618},
    {SKILL_SKINNING, 200, 300, 25, 10768},
    {SKILL_SKINNING, 275, 375, 40, 32678},
    {SKILL_SKINNING, 350, 450, 55, 50305},
}};

std::unordered_map<uint32, std::string> const ProfessionTravelAliases = {
    {1, "Kharanos"}, {11, "Menethil Harbor"}, {14, "Razor Hill"}, {17, "The Crossroads"},
    {33, "Grom'gol Base Camp"}, {38, "Thelsamar"}, {45, "Hammerfall"}, {46, "Flame Crest"},
    {47, "The Hinterlands"}, {51, "Stonard"}, {67, "K3"}, {85, "Brill"},
    {130, "The Sepulcher"}, {139, "Light's Hope Chapel"}, {148, "Auberdine"},
    {210, "Icecrown"}, {215, "Bloodhoof Village"}, {267, "Tarren Mill"},
    {331, "Astranaar"}, {357, "Camp Mojache"}, {361, "Bloodvenom Post"},
    {394, "Conquest Hold"}, {400, "Freewind Post"}, {406, "Sun Rock Retreat"},
    {440, "Gadgetzan"}, {490, "Marshal's Refuge"}, {495, "Camp Winterhoof"},
    {618, "Everlook"}, {3483, "Thrallmar"}, {3518, "Garadar"},
    {3519, "Stonebreaker Hold"}, {3521, "Zabra'jin"}, {3522, "Thunderlord Stronghold"},
    {3523, "Area 52"}, {3537, "Warsong Hold"}, {3711, "River's Heart"},
};

std::optional<IntentType> ParseIntentType(std::string const& value)
{
    if (value == "FOLLOW")
        return IntentType::Follow;
    if (value == "HOLD_POSITION")
        return IntentType::HoldPosition;
    if (value == "ATTACK_PLAYER_TARGET")
        return IntentType::AttackPlayerTarget;
    if (value == "PULL_PLAYER_TARGET")
        return IntentType::PullPlayerTarget;
    if (value == "RETREAT")
        return IntentType::Retreat;
    if (value == "PREPARE_PARTY")
        return IntentType::PrepareParty;
    if (value == "POLYMORPH_PLAYER_TARGET")
        return IntentType::PolymorphPlayerTarget;
    if (value == "SAP_PLAYER_TARGET")
        return IntentType::SapPlayerTarget;
    if (value == "STUN_PLAYER_TARGET")
        return IntentType::StunPlayerTarget;
    if (value == "SLOW_FALL_ISSUER")
        return IntentType::SlowFallIssuer;
    if (value == "POWER_UP")
        return IntentType::PowerUp;
    if (value == "START_FARMING")
        return IntentType::StartFarming;
    if (value == "STOP_FARMING")
        return IntentType::StopFarming;
    if (value == "START_ECONOMY")
        return IntentType::StartEconomy;
    if (value == "STOP_ECONOMY")
        return IntentType::StopEconomy;
    if (value == "WORK_AUCTION_HOUSE")
        return IntentType::WorkAuctionHouse;
    if (value == "CRAFT_SUPPLIES")
        return IntentType::CraftSupplies;
    if (value == "COLLECT_MAIL")
        return IntentType::CollectMail;
    if (value == "DEPOSIT_GUILD_BANK")
        return IntentType::DepositGuildBank;
    if (value == "SHARE_GOLD")
        return IntentType::ShareGold;
    if (value == "REPORT_TO_GROUP")
        return IntentType::ReportToGroup;
    if (value == "CONTINUE_ROUTINE")
        return IntentType::ContinueRoutine;

    return std::nullopt;
}

bool IsTerminalStatus(IntentStatus status)
{
    return status == IntentStatus::Succeeded || status == IntentStatus::Failed ||
        status == IntentStatus::Rejected || status == IntentStatus::Expired ||
        status == IntentStatus::Preempted;
}

uint8 ClampPercent(float value)
{
    return static_cast<uint8>(std::clamp(value, 0.0f, 100.0f));
}

ObjectGuid PlayerGuid(uint32 lowGuid)
{
    return ObjectGuid::Create<HighGuid::Player>(lowGuid);
}

bool HasGuildOfficerAuthority(Player* issuer, Player* bot)
{
    if (!issuer || !bot || !issuer->GetGuildId() || issuer->GetGuildId() != bot->GetGuildId())
        return false;

    Guild* guild = sGuildMgr->GetGuildById(bot->GetGuildId());
    Guild::Member const* member = guild ? guild->GetMember(issuer->GetGUID()) : nullptr;
    // WotLK guild ranks are ordered by authority: 0 is Guild Master and 1 is
    // the standard Officer rank. Lower numeric IDs are always more senior.
    return member && member->GetRankId() <= 1;
}

class CadiaPlayerDirectorWorldScript : public WorldScript
{
public:
    CadiaPlayerDirectorWorldScript() : WorldScript(
        "CadiaPlayerDirectorWorldScript",
        {
            WORLDHOOK_ON_BEFORE_CONFIG_LOAD,
            WORLDHOOK_ON_STARTUP,
            WORLDHOOK_ON_UPDATE
        })
    {
    }

    void OnBeforeConfigLoad(bool reload) override
    {
        directorConfig.Initialize(reload);
    }

    void OnStartup() override
    {
        if (!IsEnabled())
        {
            LOG_INFO("module.cadia-director", "Cadia Player Director is disabled");
            return;
        }

        RecoverInterruptedIntents();
        LOG_INFO("module.cadia-director", "Cadia Player Director is enabled");
    }

    void OnUpdate(uint32 diff) override
    {
        _queryProcessor.ProcessReadyCallbacks();
        VerifyRunningIntents();

        if (!IsEnabled())
            return;

        if (_intentPollTimer > diff)
            _intentPollTimer -= diff;
        else
        {
            _intentPollTimer = directorConfig.GetConfigValue<uint32>(DirectorConfigKey::PollIntervalMs);
            PollIntents();
        }

        if (_snapshotTimer > diff)
            _snapshotTimer -= diff;
        else
        {
            _snapshotTimer = directorConfig.GetConfigValue<uint32>(DirectorConfigKey::SnapshotIntervalMs);
            PollPersonaBindingsForSnapshots();
        }

        if (_economyTimer > diff)
            _economyTimer -= diff;
        else
        {
            _economyTimer = directorConfig.GetConfigValue<uint32>(DirectorConfigKey::EconomyIntervalMs);
            PollEconomyProfiles();
        }

        if (_professionTimer > diff)
            _professionTimer -= diff;
        else
        {
            _professionTimer = directorConfig.GetConfigValue<uint32>(DirectorConfigKey::ProfessionIntervalMs);
            PollProfessionObjectives();
            PollMaterialKitTargets();
        }
    }

private:
    bool IsEnabled() const
    {
        return directorConfig.GetConfigValue<bool>(DirectorConfigKey::Enabled);
    }

    void RecoverInterruptedIntents()
    {
        auto transaction = CharacterDatabase.BeginTransaction();
        transaction->Append(
            "INSERT INTO synthetic_intent_events (intent_id, status, result_code) "
            "SELECT id, 4, 'executor_restarted' FROM synthetic_intents WHERE status IN (1, 2)");
        transaction->Append(
            "UPDATE synthetic_intents SET status = 4, result_code = 'executor_restarted', "
            "completed_at = CURRENT_TIMESTAMP WHERE status IN (1, 2)");
        CharacterDatabase.CommitTransaction(transaction);
    }

    void PollIntents()
    {
        if (_intentQueryInFlight)
            return;

        _intentQueryInFlight = true;
        uint32 const batchSize = directorConfig.GetConfigValue<uint32>(DirectorConfigKey::BatchSize);
        std::string const query = Acore::StringFormat(
            "SELECT i.id, i.issuer_guid, i.bot_guid, i.intent_type, i.parameters_json, "
            "i.expires_at <= CURRENT_TIMESTAMP, EXISTS(SELECT 1 FROM synthetic_persona_bindings b "
            "JOIN characters c ON c.guid = b.character_guid "
            "WHERE b.character_guid = i.bot_guid AND LOWER(b.persona_name) = LOWER(i.bot_name) "
            "AND LOWER(c.name) = LOWER(i.bot_name) AND b.race_id = c.race "
            "AND b.class_id = c.class AND b.gender_id = c.gender "
            "AND LOWER(b.persona_name) IN ('lyra', 'celene', 'ray', 'browntown')), "
            "EXISTS(SELECT 1 FROM synthetic_command_authorities a "
            "WHERE a.character_guid = i.issuer_guid AND a.authority_role = 'CADIA' AND a.enabled = 1) "
            "FROM synthetic_intents i WHERE i.status = 0 ORDER BY i.id ASC LIMIT {}",
            batchSize);

        _queryProcessor.AddCallback(CharacterDatabase.AsyncQuery(query).WithCallback(
            [this](QueryResult result)
            {
                _intentQueryInFlight = false;
                ProcessIntentRows(result);
            }));
    }

    void ProcessIntentRows(QueryResult result)
    {
        if (!result)
            return;

        do
        {
            Field* fields = result->Fetch();
            IntentRow const row{
                fields[0].Get<uint64>(),
                fields[1].Get<uint32>(),
                fields[2].Get<uint32>(),
                fields[3].Get<std::string>(),
                fields[4].Get<std::string>(),
                fields[5].Get<bool>(),
                fields[6].Get<bool>(),
                fields[7].Get<bool>()
            };
            if (!RememberHandledIntent(row.id))
                continue;
            ExecuteIntent(row);
        } while (result->NextRow());
    }

    void ExecuteIntent(IntentRow const& row)
    {
        if (row.expired)
        {
            SetIntentStatus(row.id, IntentStatus::Expired, "intent_expired");
            return;
        }

        if (!row.bindingValid)
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "binding_invalid");
            return;
        }

        if (row.parameters != "{}")
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "parameters_not_supported");
            return;
        }

        std::optional<IntentType> const intentType = ParseIntentType(row.type);
        if (!intentType)
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "intent_unknown");
            return;
        }

        Player* issuer = ObjectAccessor::FindPlayer(PlayerGuid(row.issuerGuid));
        if (!issuer)
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "issuer_offline");
            return;
        }

        if (sPlayerbotsMgr.GetPlayerbotAI(issuer) && !row.cadiaAuthority)
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "issuer_is_bot");
            return;
        }

        Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(row.botGuid));
        if (!bot)
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "bot_offline");
            return;
        }

        PlayerbotAI* botAI = sPlayerbotsMgr.GetPlayerbotAI(bot);
        if (!botAI)
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "playerbot_ai_missing");
            return;
        }

        Group* group = issuer->GetGroup();
        bool const sameGroup = group && group == bot->GetGroup();
        bool const isMaster = sameGroup && botAI->GetMaster() == issuer;
        bool const hasGroupRank = sameGroup &&
            (group->IsLeader(issuer->GetGUID()) || group->IsAssistant(issuer->GetGUID()));
        bool groupAuthority = isMaster || hasGroupRank;
        if (isMaster && !botAI->GetSecurity()->CheckLevelFor(PLAYERBOT_SECURITY_ALLOW_ALL, true, issuer))
            groupAuthority = false;

        // Guild Officer/GM authority is sufficient without a shared group for
        // every typed command except a transfer of the bot's own gold.
        bool const guildOfficerAuthority = *intentType != IntentType::ShareGold &&
            HasGuildOfficerAuthority(issuer, bot);
        if (!groupAuthority && !guildOfficerAuthority && !row.cadiaAuthority)
        {
            SetIntentStatus(
                row.id,
                IntentStatus::Rejected,
                sameGroup ? "authority_denied" : "not_grouped_or_guild_officer");
            return;
        }

        if (bot->isDead())
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "bot_dead");
            return;
        }

        PreemptRunningIntent(row.botGuid);
        SetIntentStatus(row.id, IntentStatus::Accepted, "accepted");
        Event const event("cadia director", "", issuer);

        switch (*intentType)
        {
            case IntentType::Follow:
                ExecuteImmediateStrategy(
                    row.id,
                    botAI,
                    "follow chat shortcut",
                    "follow",
                    "follow_strategy_active",
                    event);
                return;
            case IntentType::HoldPosition:
                ExecuteImmediateStrategy(
                    row.id,
                    botAI,
                    "stay chat shortcut",
                    "stay",
                    "hold_strategy_active",
                    event);
                return;
            case IntentType::Retreat:
                ExecuteImmediateStrategy(
                    row.id,
                    botAI,
                    "flee chat shortcut",
                    "passive",
                    "retreat_strategy_active",
                    event);
                return;
            case IntentType::PrepareParty:
                ExecutePrepareParty(row.id, bot, botAI);
                return;
            case IntentType::PolymorphPlayerTarget:
            case IntentType::SapPlayerTarget:
            case IntentType::StunPlayerTarget:
                ExecuteCrowdControlIntent(row, *intentType, issuer, bot, botAI, event);
                return;
            case IntentType::SlowFallIssuer:
                ExecuteSlowFall(row, issuer, bot, botAI);
                return;
            case IntentType::PowerUp:
                ExecutePowerUp(row.id, botAI);
                return;
            case IntentType::StartFarming:
                ExecuteFarming(row.id, botAI, true);
                return;
            case IntentType::StopFarming:
                ExecuteFarming(row.id, botAI, false);
                return;
            case IntentType::StartEconomy:
                ExecuteEconomyMode(row.id, bot, botAI, true);
                return;
            case IntentType::StopEconomy:
                ExecuteEconomyMode(row.id, bot, botAI, false);
                return;
            case IntentType::WorkAuctionHouse:
                ExecuteAuctionHouseWork(row.id, bot, botAI);
                return;
            case IntentType::CraftSupplies:
                ExecuteCraftSupplies(row.id, bot, botAI, event);
                return;
            case IntentType::CollectMail:
                ExecuteCollectMail(row.id, bot, botAI, event);
                return;
            case IntentType::DepositGuildBank:
                ExecuteDepositGuildBank(row.id, bot);
                return;
            case IntentType::ShareGold:
                ExecuteShareGold(row.id, issuer, bot);
                return;
            case IntentType::ReportToGroup:
                ExecuteReportToGroup(row.id, issuer, bot, botAI);
                return;
            case IntentType::ContinueRoutine:
                ExecuteContinueRoutine(row.id, issuer, bot, botAI);
                return;
            case IntentType::AttackPlayerTarget:
            case IntentType::PullPlayerTarget:
                ExecuteTargetIntent(row, *intentType, issuer, bot, botAI, event);
                return;
        }
    }

    void ExecuteReportToGroup(uint64 intentId, Player* issuer, Player* bot, PlayerbotAI* botAI)
    {
        Group* group = issuer->GetGroup();
        if (!group || group != bot->GetGroup())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "not_in_same_group");
            return;
        }
        if (bot->IsInCombat())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "in_combat");
            return;
        }

        GroupDutyState& state = _groupDutyStates[bot->GetGUID().GetCounter()];
        state.mode = GroupDutyMode::Reporting;
        state.groupGuid = group->GetGUID().GetRawValue();
        state.masterGuid = issuer->GetGUID().GetCounter();

        botAI->ChangeStrategy("-travel,-grind,+gather,+loot,+follow,-stay,-passive", BOT_STATE_NON_COMBAT);
        bool teleported = true;
        if (bot->GetMapId() != issuer->GetMapId() ||
            bot->GetDistance(issuer) > sPlayerbotAIConfig.sightDistance)
        {
            teleported = bot->TeleportTo(
                issuer->GetMapId(),
                issuer->GetPositionX(),
                issuer->GetPositionY(),
                issuer->GetPositionZ(),
                issuer->GetOrientation());
        }
        botAI->SetNextCheckDelay(0);
        PersistGroupDutyState(bot, state, teleported ? "group_duty_active" : "report_teleport_failed");
        SetIntentStatus(
            intentId,
            teleported ? IntentStatus::Succeeded : IntentStatus::Rejected,
            teleported ? "reported_to_group" : "report_teleport_failed");
    }

    void ExecuteContinueRoutine(uint64 intentId, Player* issuer, Player* bot, PlayerbotAI* botAI)
    {
        Group* group = issuer->GetGroup();
        if (!group || group != bot->GetGroup())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "not_in_same_group");
            return;
        }

        GroupDutyState& state = _groupDutyStates[bot->GetGUID().GetCounter()];
        state.mode = GroupDutyMode::RoutineWhileGrouped;
        state.groupGuid = group->GetGUID().GetRawValue();
        state.masterGuid = issuer->GetGUID().GetCounter();
        ApplyRoutineStrategies(botAI);
        PersistGroupDutyState(bot, state, "routine_continuing");
        _professionTimer = 0;
        SetIntentStatus(intentId, IntentStatus::Succeeded, "routine_continuing");
    }

    void ExecuteImmediateStrategy(
        uint64 intentId,
        PlayerbotAI* botAI,
        std::string const& action,
        std::string const& expectedStrategy,
        std::string const& successCode,
        Event const& event)
    {
        bool const executed = botAI->DoSpecificAction(action, event, true);
        bool const verified = botAI->HasStrategy(expectedStrategy, BOT_STATE_NON_COMBAT) ||
            botAI->HasStrategy(expectedStrategy, BOT_STATE_COMBAT);
        SetIntentStatus(
            intentId,
            executed && verified ? IntentStatus::Succeeded : IntentStatus::Rejected,
            executed && verified ? successCode : "action_rejected");
    }

    void ExecutePrepareParty(uint64 intentId, Player* bot, PlayerbotAI* botAI)
    {
        if (bot->IsInCombat())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "in_combat");
            return;
        }

        std::string strategy;
        switch (bot->getClass())
        {
            case CLASS_PALADIN:
                strategy = "bkings";
                break;
            case CLASS_PRIEST:
            case CLASS_MAGE:
            case CLASS_DRUID:
                strategy = "buff";
                break;
            default:
                SetIntentStatus(intentId, IntentStatus::Rejected, "prepare_strategy_unavailable");
                return;
        }

        botAI->ChangeStrategy("+" + strategy, BOT_STATE_NON_COMBAT);
        botAI->SetNextCheckDelay(0);
        bool const verified = botAI->HasStrategy(strategy, BOT_STATE_NON_COMBAT);
        SetIntentStatus(
            intentId,
            verified ? IntentStatus::Succeeded : IntentStatus::Rejected,
            verified ? "prepare_strategy_active" : "action_rejected");
    }

    void BeginVerification(IntentRow const& row, IntentType type, Unit* target)
    {
        SetIntentStatus(row.id, IntentStatus::Running, "action_started");
        uint32 const timeout = directorConfig.GetConfigValue<uint32>(DirectorConfigKey::VerificationTimeoutMs);
        _pendingVerifications[row.botGuid] = PendingVerification{
            row.id,
            type,
            row.issuerGuid,
            row.botGuid,
            target->GetGUID(),
            std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout)
        };
    }

    Unit* ValidateHostileSelectedTarget(uint64 intentId, Player* issuer, Player* bot)
    {
        Unit* target = issuer->GetSelectedUnit();
        if (!target || !target->IsInWorld())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "no_player_target");
            return nullptr;
        }

        if (!bot->IsValidAttackTarget(target))
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "target_not_hostile");
            return nullptr;
        }
        return target;
    }

    void ExecuteCrowdControlIntent(
        IntentRow const& row,
        IntentType intentType,
        Player* issuer,
        Player* bot,
        PlayerbotAI* botAI,
        Event const& event)
    {
        Unit* target = ValidateHostileSelectedTarget(row.id, issuer, bot);
        if (!target)
            return;

        if (intentType == IntentType::PolymorphPlayerTarget)
        {
            if (bot->getClass() != CLASS_MAGE)
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "wrong_class");
                return;
            }
            if (!botAI->HasSpell("polymorph"))
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "spell_not_known");
                return;
            }
            if (!botAI->CastSpell("polymorph", target))
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "spell_not_ready");
                return;
            }
        }
        else if (intentType == IntentType::SapPlayerTarget)
        {
            if (bot->getClass() != CLASS_ROGUE)
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "wrong_class");
                return;
            }
            if (!botAI->HasSpell("sap"))
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "spell_not_known");
                return;
            }
            if (bot->IsInCombat() || target->IsInCombat())
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "spell_not_ready");
                return;
            }

            Group* group = bot->GetGroup();
            group->SetTargetIcon(RtiTargetValue::moonIndex, issuer->GetGUID(), target->GetGUID());
            botAI->GetAiObjectContext()->GetValue<std::string>("rti cc")->Set("moon");
            botAI->ChangeStrategy("+cc", BOT_STATE_NON_COMBAT);
            botAI->SetNextCheckDelay(0);
        }
        else
        {
            if (bot->getClass() != CLASS_ROGUE)
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "wrong_class");
                return;
            }

            bool castStarted = false;
            if (botAI->CanCastSpell("kidney shot", target))
                castStarted = botAI->CastSpell("kidney shot", target);
            else if (botAI->CanCastSpell("cheap shot", target))
                castStarted = botAI->CastSpell("cheap shot", target);
            else
            {
                botAI->GetAiObjectContext()->GetValue<Unit*>("current target")->Set(target);
                castStarted = botAI->DoSpecificAction("attack", event, true);
            }

            if (!castStarted)
            {
                SetIntentStatus(row.id, IntentStatus::Rejected, "spell_not_ready");
                return;
            }
        }

        BeginVerification(row, intentType, target);
    }

    void ExecuteSlowFall(IntentRow const& row, Player* issuer, Player* bot, PlayerbotAI* botAI)
    {
        if (bot->getClass() != CLASS_MAGE)
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "wrong_class");
            return;
        }
        if (!botAI->HasSpell("slow fall"))
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "spell_not_known");
            return;
        }
        if (!botAI->CastSpell("slow fall", issuer))
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "spell_not_ready");
            return;
        }

        BeginVerification(row, IntentType::SlowFallIssuer, issuer);
    }

    void ExecutePowerUp(uint64 intentId, PlayerbotAI* botAI)
    {
        botAI->ChangeStrategy("+boost", BOT_STATE_COMBAT);
        botAI->SetNextCheckDelay(0);
        bool const verified = botAI->HasStrategy("boost", BOT_STATE_COMBAT);
        SetIntentStatus(
            intentId,
            verified ? IntentStatus::Succeeded : IntentStatus::Rejected,
            verified ? "boost_strategy_active" : "action_rejected");
    }

    void ExecuteFarming(uint64 intentId, PlayerbotAI* botAI, bool enable)
    {
        if (enable)
        {
            botAI->ChangeStrategy("+grind,+gather,-follow,-stay,-passive", BOT_STATE_NON_COMBAT);
            botAI->SetNextCheckDelay(0);
            bool const verified = botAI->HasStrategy("grind", BOT_STATE_NON_COMBAT) &&
                botAI->HasStrategy("gather", BOT_STATE_NON_COMBAT);
            SetIntentStatus(
                intentId,
                verified ? IntentStatus::Succeeded : IntentStatus::Rejected,
                verified ? "farming_strategy_active" : "action_rejected");
            return;
        }

        botAI->ChangeStrategy("-grind,-gather,+follow,-stay,-passive", BOT_STATE_NON_COMBAT);
        botAI->SetNextCheckDelay(0);
        bool const verified = !botAI->HasStrategy("grind", BOT_STATE_NON_COMBAT) &&
            !botAI->HasStrategy("gather", BOT_STATE_NON_COMBAT) &&
            botAI->HasStrategy("follow", BOT_STATE_NON_COMBAT);
        SetIntentStatus(
            intentId,
            verified ? IntentStatus::Succeeded : IntentStatus::Rejected,
            verified ? "farming_strategy_stopped" : "action_rejected");
    }

    EconomyProfile GetEconomyProfile(Player* bot) const
    {
        auto const profile = _economyProfiles.find(bot->GetGUID().GetCounter());
        if (profile != _economyProfiles.end())
            return profile->second;

        EconomyProfile fallback;
        fallback.botGuid = bot->GetGUID().GetCounter();
        return fallback;
    }

    void ExecuteEconomyMode(uint64 intentId, Player* bot, PlayerbotAI* botAI, bool enable)
    {
        EconomyProfile profile = GetEconomyProfile(bot);
        _economyProfiles[profile.botGuid] = profile;

        CharacterDatabase.Execute(Acore::StringFormat(
            "INSERT INTO synthetic_economy_profiles (bot_guid, bot_name, enabled) "
            "VALUES ({}, '{}', {}) ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), "
            "bot_name = VALUES(bot_name), updated_at = CURRENT_TIMESTAMP",
            profile.botGuid,
            bot->GetName(),
            enable ? 1 : 0));

        if (enable)
            botAI->ChangeStrategy("+grind,+gather,-stay,-passive", BOT_STATE_NON_COMBAT);
        else
            botAI->ChangeStrategy("-grind,-gather,+follow,-stay,-passive", BOT_STATE_NON_COMBAT);
        botAI->SetNextCheckDelay(0);

        bool const strategiesVerified = enable ?
            botAI->HasStrategy("grind", BOT_STATE_NON_COMBAT) &&
                botAI->HasStrategy("gather", BOT_STATE_NON_COMBAT) :
            !botAI->HasStrategy("grind", BOT_STATE_NON_COMBAT) &&
                !botAI->HasStrategy("gather", BOT_STATE_NON_COMBAT);

        SetIntentStatus(
            intentId,
            strategiesVerified ? IntentStatus::Succeeded : IntentStatus::Rejected,
            strategiesVerified ? (enable ? "economy_enabled" : "economy_disabled") : "action_rejected");
    }

    std::optional<AuctionContext> GetAuctionContext(Player* bot) const
    {
        AuctionHouseId const requestedHouse = bot->GetTeamId() == TEAM_ALLIANCE ?
            AuctionHouseId::Alliance : AuctionHouseId::Horde;
        AuctionHouseEntry const* entry = AuctionHouseMgr::GetAuctionHouseEntryFromHouse(requestedHouse);
        if (!entry)
            return std::nullopt;

        AuctionHouseId const actualHouse = static_cast<AuctionHouseId>(entry->houseId);
        AuctionHouseObject* house = sAuctionMgr->GetAuctionsMapByHouseId(actualHouse);
        if (!house)
            return std::nullopt;

        return AuctionContext{actualHouse, entry, house};
    }

    Item* SelectAuctionItem(Player* bot, PlayerbotAI* botAI) const
    {
        Item* best = nullptr;
        uint64 bestVendorValue = 0;
        auto consider = [&](Item* item)
        {
            if (!item || !item->CanBeTraded() || item->IsInTrade() || item->IsNotEmptyBag() ||
                item->GetTemplate()->HasFlag(ITEM_FLAG_CONJURED) || item->GetUInt32Value(ITEM_FIELD_DURATION))
                return;

            ItemUsage const usage = botAI->GetAiObjectContext()
                ->GetValue<ItemUsage>("item usage", item->GetEntry())->Get();
            if (usage != ITEM_USAGE_AH)
                return;

            uint64 const vendorValue = static_cast<uint64>(item->GetTemplate()->SellPrice) * item->GetCount();
            if (!best || vendorValue > bestVendorValue)
            {
                best = item;
                bestVendorValue = vendorValue;
            }
        };

        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            consider(bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));

        for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        {
            Bag* bag = bot->GetBagByPos(bagSlot);
            if (!bag)
                continue;
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                consider(bag->GetItemByPos(slot));
        }

        return best;
    }

    bool TryListAuction(
        Player* bot,
        PlayerbotAI* botAI,
        EconomyProfile const& profile,
        EconomyResult& result)
    {
        std::optional<AuctionContext> const context = GetAuctionContext(bot);
        if (!context)
            return false;

        uint32 ownedAuctions = 0;
        for (auto const& auction : context->house->GetAuctions())
            if (auction.second->owner == bot->GetGUID())
                ++ownedAuctions;
        if (ownedAuctions >= profile.maxOwnedAuctions)
            return false;

        Item* item = SelectAuctionItem(bot, botAI);
        if (!item)
            return false;

        ItemTemplate const* itemTemplate = item->GetTemplate();
        uint32 const itemCount = item->GetCount();
        uint64 lowestUnitBuyout = 0;
        for (auto const& auction : context->house->GetAuctions())
        {
            AuctionEntry const* entry = auction.second;
            if (entry->item_template != item->GetEntry() || !entry->buyout || !entry->itemCount)
                continue;

            uint64 const unitBuyout = entry->buyout / entry->itemCount;
            if (!lowestUnitBuyout || unitBuyout < lowestUnitBuyout)
                lowestUnitBuyout = unitBuyout;
        }

        uint64 unitBuyout = lowestUnitBuyout ? std::max<uint64>(1, lowestUnitBuyout * 99 / 100) :
            std::max<uint64>(100, static_cast<uint64>(itemTemplate->SellPrice) * 4);
        uint32 const buyout = static_cast<uint32>(std::min<uint64>(MAX_MONEY_AMOUNT, unitBuyout * itemCount));
        uint32 const startBid = std::max<uint32>(1, buyout * 4 / 5);
        uint32 const baseDuration = 2 * MIN_AUCTION_TIME;
        uint32 const deposit = sAuctionMgr->GetAuctionDeposit(context->entry, baseDuration, item, itemCount);
        uint64 const botMoney = bot->GetMoney();
        if (botMoney < profile.minimumReserve + deposit)
            return false;

        bot->ModifyMoney(-static_cast<int32>(deposit));

        AuctionEntry* auction = new AuctionEntry;
        auction->Id = sObjectMgr->GenerateAuctionID();
        auction->houseId = context->houseId;
        auction->item_guid = item->GetGUID();
        auction->item_template = item->GetEntry();
        auction->itemCount = itemCount;
        auction->owner = bot->GetGUID();
        auction->startbid = startBid;
        auction->bid = 0;
        auction->buyout = buyout;
        auction->expire_time = GameTime::GetGameTime().count() +
            static_cast<uint32>(baseDuration * sWorld->getRate(RATE_AUCTION_TIME));
        auction->bidder = ObjectGuid::Empty;
        auction->deposit = deposit;
        auction->auctionHouseEntry = context->entry;

        sAuctionMgr->AddAItem(item);
        context->house->AddAuction(auction);
        bot->MoveItemFromInventory(item->GetBagSlot(), item->GetSlot(), true);

        CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
        item->DeleteFromInventoryDB(transaction);
        item->SaveToDB(transaction);
        auction->SaveToDB(transaction);
        bot->SaveInventoryAndGoldToDB(transaction);
        CharacterDatabase.CommitTransaction(transaction);
        bot->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_CREATE_AUCTION, 1);

        result.resultCode = "auction_listed";
        result.actionKind = "AH_LIST";
        result.itemEntry = item->GetEntry();
        result.itemCount = itemCount;
        result.copperDelta = -static_cast<int64>(deposit);
        LOG_INFO(
            "module.cadia-director",
            "{} listed item {} x{} as character-owned auction {} for {} copper",
            bot->GetName(),
            result.itemEntry,
            result.itemCount,
            auction->Id,
            buyout);
        return true;
    }

    bool TryBuyAuction(Player* bot, PlayerbotAI* botAI, EconomyProfile const& profile, EconomyResult& result)
    {
        std::optional<AuctionContext> const context = GetAuctionContext(bot);
        if (!context)
            return false;

        AuctionEntry* best = nullptr;
        uint8 bestPriority = 0;
        for (auto const& auction : context->house->GetAuctions())
        {
            AuctionEntry* entry = auction.second;
            if (!entry->buyout || entry->owner == bot->GetGUID() ||
                _economyProfiles.contains(entry->owner.GetCounter()))
                continue;
            if (sCharacterCache->GetCharacterAccountIdByGuid(entry->owner) == bot->GetSession()->GetAccountId())
                continue;
            if (entry->buyout > profile.maxSpendPerCycle ||
                bot->GetMoney() < profile.minimumReserve + entry->buyout)
                continue;

            ItemUsage const usage = botAI->GetAiObjectContext()
                ->GetValue<ItemUsage>("item usage", entry->item_template)->Get();
            uint8 priority = 0;
            if (usage == ITEM_USAGE_REPLACE || usage == ITEM_USAGE_EQUIP)
                priority = 4;
            else if (usage == ITEM_USAGE_SKILL)
                priority = 3;
            else if (usage == ITEM_USAGE_USE || usage == ITEM_USAGE_AMMO)
                priority = 2;
            if (!priority)
                continue;

            if (!best || priority > bestPriority ||
                (priority == bestPriority && entry->buyout < best->buyout))
            {
                best = entry;
                bestPriority = priority;
            }
        }

        if (!best)
            return false;

        uint32 const auctionId = best->Id;
        uint32 const itemEntry = best->item_template;
        uint32 const itemCount = best->itemCount;
        uint32 const buyout = best->buyout;
        ObjectGuid const seller = best->owner;
        CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();

        uint32 const requiredPayment = best->bidder == bot->GetGUID() ?
            best->buyout - best->bid : best->buyout;
        bot->ModifyMoney(-static_cast<int32>(requiredPayment));
        if (best->bidder && best->bidder != bot->GetGUID())
            sAuctionMgr->SendAuctionOutbiddedMail(best, best->buyout, bot, transaction);
        best->bidder = bot->GetGUID();
        best->bid = best->buyout;
        bot->UpdateAchievementCriteria(ACHIEVEMENT_CRITERIA_TYPE_HIGHEST_AUCTION_BID, best->buyout);

        sAuctionMgr->SendAuctionSalePendingMail(best, transaction);
        sAuctionMgr->SendAuctionSuccessfulMail(best, transaction);
        sAuctionMgr->SendAuctionWonMail(best, transaction);
        sScriptMgr->OnAuctionSuccessful(context->house, best);
        best->DeleteFromDB(transaction);
        sAuctionMgr->RemoveAItem(best->item_guid);
        context->house->RemoveAuction(best);
        bot->SaveInventoryAndGoldToDB(transaction);
        CharacterDatabase.CommitTransaction(transaction);

        result.resultCode = "auction_bought";
        result.actionKind = "AH_BUY";
        result.itemEntry = itemEntry;
        result.itemCount = itemCount;
        result.copperDelta = -static_cast<int64>(requiredPayment);
        LOG_INFO(
            "module.cadia-director",
            "{} bought character-owned auction {} from {}: item {} x{} for {} copper",
            bot->GetName(),
            auctionId,
            seller.ToString(),
            itemEntry,
            itemCount,
            buyout);
        return true;
    }

    bool TryCraftSupplies(Player* bot, PlayerbotAI* botAI, Event const& event, EconomyResult& result)
    {
        if (bot->IsInCombat())
            return false;
        if (!botAI->DoSpecificAction("craft random item", event, true))
            return false;

        result.resultCode = "craft_started";
        result.actionKind = "CRAFT";
        return true;
    }

    void RecordEconomyResult(Player* bot, EconomyResult const& result)
    {
        CharacterDatabase.Execute(Acore::StringFormat(
            "INSERT INTO synthetic_economy_ledger "
            "(bot_guid, bot_name, action_kind, item_entry, item_count, copper_delta, result_code) "
            "VALUES ({}, '{}', '{}', {}, {}, {}, '{}')",
            bot->GetGUID().GetCounter(),
            bot->GetName(),
            result.actionKind,
            result.itemEntry,
            result.itemCount,
            result.copperDelta,
            result.resultCode));
        CharacterDatabase.Execute(Acore::StringFormat(
            "UPDATE synthetic_economy_profiles SET last_cycle_at = CURRENT_TIMESTAMP, "
            "last_result_code = '{}' WHERE bot_guid = {}",
            result.resultCode,
            bot->GetGUID().GetCounter()));
    }

    EconomyResult RunEconomyCycle(Player* bot, PlayerbotAI* botAI, bool allowCraft, Event const& event)
    {
        EconomyProfile const profile = GetEconomyProfile(bot);
        EconomyResult result;
        bool executed = false;
        if (profile.autoList)
            executed = TryListAuction(bot, botAI, profile, result);
        if (!executed && profile.autoBuy)
            executed = TryBuyAuction(bot, botAI, profile, result);
        if (!executed && allowCraft && profile.autoCraft)
            executed = TryCraftSupplies(bot, botAI, event, result);

        if (executed)
            RecordEconomyResult(bot, result);
        else
            CharacterDatabase.Execute(Acore::StringFormat(
                "UPDATE synthetic_economy_profiles SET last_cycle_at = CURRENT_TIMESTAMP, "
                "last_result_code = 'auction_no_work' WHERE bot_guid = {}",
                bot->GetGUID().GetCounter()));
        return result;
    }

    void ExecuteAuctionHouseWork(uint64 intentId, Player* bot, PlayerbotAI* botAI)
    {
        EconomyResult const result = RunEconomyCycle(bot, botAI, false, Event("cadia economy", "", bot));
        SetIntentStatus(intentId, IntentStatus::Succeeded, result.resultCode);
    }

    void ExecuteCraftSupplies(uint64 intentId, Player* bot, PlayerbotAI* botAI, Event const& event)
    {
        EconomyResult result;
        if (!TryCraftSupplies(bot, botAI, event, result))
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "craft_unavailable");
            return;
        }

        RecordEconomyResult(bot, result);
        SetIntentStatus(intentId, IntentStatus::Succeeded, result.resultCode);
    }

    void ExecuteCollectMail(uint64 intentId, Player* bot, PlayerbotAI* botAI, Event event)
    {
        size_t const mailBefore = bot->GetMailSize();
        if (!mailBefore)
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "no_delivered_mail");
            return;
        }

        Event const mailEvent(event.GetSource(), "take *", event.getOwner());
        bool const executed = botAI->DoSpecificAction("mail", mailEvent, true);
        bool const verified = executed && bot->GetMailSize() < mailBefore;
        SetIntentStatus(
            intentId,
            verified ? IntentStatus::Succeeded : IntentStatus::Rejected,
            verified ? "mail_collected" : "mailbox_not_nearby");
    }

    void ExecuteShareGold(uint64 intentId, Player* issuer, Player* bot)
    {
        EconomyProfile const profile = GetEconomyProfile(bot);
        uint64 const money = bot->GetMoney();
        if (money <= profile.minimumReserve)
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "insufficient_surplus_gold");
            return;
        }

        uint64 const gift = std::min<uint64>(profile.maxGoldGift, (money - profile.minimumReserve) / 10);
        if (gift < GOLD)
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "insufficient_surplus_gold");
            return;
        }

        CharacterDatabaseTransaction transaction = CharacterDatabase.BeginTransaction();
        bot->ModifyMoney(-static_cast<int32>(gift));
        MailDraft("A share for the group", "Useful gold belongs in useful hands.")
            .AddMoney(static_cast<uint32>(gift))
            .SendMailTo(transaction, MailReceiver(issuer), MailSender(bot));
        bot->SaveInventoryAndGoldToDB(transaction);
        CharacterDatabase.CommitTransaction(transaction);

        EconomyResult result;
        result.resultCode = "gold_shared";
        result.actionKind = "GOLD_GIFT";
        result.copperDelta = -static_cast<int64>(gift);
        RecordEconomyResult(bot, result);
        SetIntentStatus(intentId, IntentStatus::Succeeded, result.resultCode);
    }

    void ExecuteTargetIntent(
        IntentRow const& row,
        IntentType intentType,
        Player* issuer,
        Player* bot,
        PlayerbotAI* botAI,
        Event const& event)
    {
        Unit* target = ValidateHostileSelectedTarget(row.id, issuer, bot);
        if (!target)
            return;

        std::string const action = intentType == IntentType::AttackPlayerTarget ? "attack" : "pull my target";
        if (intentType == IntentType::AttackPlayerTarget)
            botAI->GetAiObjectContext()->GetValue<Unit*>("current target")->Set(target);
        if (!botAI->DoSpecificAction(action, event, true))
        {
            SetIntentStatus(row.id, IntentStatus::Rejected, "action_rejected");
            return;
        }

        BeginVerification(row, intentType, target);
    }

    void VerifyRunningIntents()
    {
        auto const now = std::chrono::steady_clock::now();
        for (auto iterator = _pendingVerifications.begin(); iterator != _pendingVerifications.end();)
        {
            PendingVerification const& pending = iterator->second;
            Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(pending.botGuid));
            PlayerbotAI* botAI = bot ? sPlayerbotsMgr.GetPlayerbotAI(bot) : nullptr;
            Unit* target = botAI ? botAI->GetUnit(pending.targetGuid) : nullptr;
            bool completed = false;
            std::string resultCode;
            IntentStatus status = IntentStatus::Running;

            if (!bot || !botAI)
            {
                completed = true;
                status = IntentStatus::Failed;
                resultCode = "bot_offline";
            }
            else if (!target)
            {
                completed = true;
                status = IntentStatus::Failed;
                resultCode = "target_unavailable";
            }
            else if (target->isDead())
            {
                completed = true;
                bool const combatIntent = pending.type == IntentType::AttackPlayerTarget ||
                    pending.type == IntentType::PullPlayerTarget;
                status = combatIntent ? IntentStatus::Succeeded : IntentStatus::Failed;
                if (pending.type == IntentType::AttackPlayerTarget)
                    resultCode = "attack_target_defeated";
                else if (pending.type == IntentType::PullPlayerTarget)
                    resultCode = "pull_target_defeated";
                else
                    resultCode = "target_unavailable";
            }
            else if (pending.type == IntentType::PolymorphPlayerTarget && target->IsPolymorphed())
            {
                completed = true;
                status = IntentStatus::Succeeded;
                resultCode = "target_polymorphed";
            }
            else if (pending.type == IntentType::SapPlayerTarget &&
                target->HasAuraWithMechanic(1ULL << MECHANIC_SAPPED))
            {
                completed = true;
                status = IntentStatus::Succeeded;
                resultCode = "target_sapped";
            }
            else if (pending.type == IntentType::StunPlayerTarget &&
                target->HasUnitState(UNIT_STATE_STUNNED))
            {
                completed = true;
                status = IntentStatus::Succeeded;
                resultCode = "target_stunned";
            }
            else if (pending.type == IntentType::SlowFallIssuer && botAI->HasAura("slow fall", target))
            {
                completed = true;
                status = IntentStatus::Succeeded;
                resultCode = "slow_fall_active";
            }
            else if ((pending.type == IntentType::AttackPlayerTarget ||
                pending.type == IntentType::PullPlayerTarget) && target->IsInCombat() &&
                (bot->GetTarget() == target->GetGUID() || target->GetTarget() == bot->GetGUID()))
            {
                completed = true;
                status = IntentStatus::Succeeded;
                resultCode = pending.type == IntentType::AttackPlayerTarget ?
                    "attack_engaged" : "pull_engaged";
            }
            else if (now >= pending.deadline)
            {
                completed = true;
                status = IntentStatus::Failed;
                resultCode = "verification_timeout";
            }

            if (completed)
            {
                SetIntentStatus(pending.intentId, status, resultCode);
                CaptureBotState(pending.botGuid);
                iterator = _pendingVerifications.erase(iterator);
            }
            else
                ++iterator;
        }
    }

    void PreemptRunningIntent(uint32 botGuid)
    {
        auto const iterator = _pendingVerifications.find(botGuid);
        if (iterator == _pendingVerifications.end())
            return;

        SetIntentStatus(
            iterator->second.intentId,
            IntentStatus::Preempted,
            "preempted_by_new_intent");
        _pendingVerifications.erase(iterator);
    }

    void SetIntentStatus(uint64 intentId, IntentStatus status, std::string const& resultCode)
    {
        uint32 const statusValue = static_cast<uint32>(status);
        std::string timestampUpdate;
        if (status == IntentStatus::Accepted)
            timestampUpdate = ", accepted_at = CURRENT_TIMESTAMP";
        else if (IsTerminalStatus(status))
            timestampUpdate = ", completed_at = CURRENT_TIMESTAMP";

        auto transaction = CharacterDatabase.BeginTransaction();
        transaction->Append(Acore::StringFormat(
            "UPDATE synthetic_intents SET status = {}, result_code = '{}'{} WHERE id = {}",
            statusValue,
            resultCode,
            timestampUpdate,
            intentId));
        transaction->Append(Acore::StringFormat(
            "INSERT INTO synthetic_intent_events (intent_id, status, result_code) "
            "VALUES ({}, {}, '{}')",
            intentId,
            statusValue,
            resultCode));
        CharacterDatabase.CommitTransaction(transaction);
    }

    bool RememberHandledIntent(uint64 intentId)
    {
        if (!_handledIntentIds.insert(intentId).second)
            return false;

        _handledIntentOrder.push_back(intentId);
        while (_handledIntentOrder.size() > 4096)
        {
            _handledIntentIds.erase(_handledIntentOrder.front());
            _handledIntentOrder.pop_front();
        }
        return true;
    }

    void PersistGroupDutyState(Player* bot, GroupDutyState const& state, std::string const& status)
    {
        CharacterDatabase.Execute(Acore::StringFormat(
            "INSERT INTO synthetic_bot_routine_state "
            "(bot_guid, group_mode, group_guid, master_guid, routine_kind, routine_zone, status, "
            "taxi_nodes_known, random_events_suppressed) "
            "VALUES ({}, {}, {}, {}, 'MATERIAL_KITS', {}, '{}', 1, 1) "
            "ON DUPLICATE KEY UPDATE captured_at = CURRENT_TIMESTAMP, "
            "group_mode = VALUES(group_mode), group_guid = VALUES(group_guid), "
            "master_guid = VALUES(master_guid), routine_kind = VALUES(routine_kind), "
            "routine_zone = VALUES(routine_zone), status = VALUES(status), "
            "taxi_nodes_known = VALUES(taxi_nodes_known), "
            "random_events_suppressed = VALUES(random_events_suppressed)",
            bot->GetGUID().GetCounter(),
            static_cast<uint32>(state.mode),
            state.groupGuid,
            state.masterGuid,
            bot->GetZoneId(),
            status));
    }

    bool GrantAllFactionTaxiNodes(Player* bot)
    {
        if (!directorConfig.GetConfigValue<bool>(DirectorConfigKey::ProfessionGrantTaxiNodes))
            return false;

        bool changed = false;
        uint8 const mountIndex = bot->GetTeamId() == TEAM_ALLIANCE ? 1 : 0;
        for (uint32 nodeId = 1; nodeId < sTaxiNodesStore.GetNumRows(); ++nodeId)
        {
            TaxiNodesEntry const* node = sTaxiNodesStore.LookupEntry(nodeId);
            if (!node || !node->MountCreatureID[mountIndex])
                continue;

            uint8 const field = uint8((nodeId - 1) / 32);
            uint32 const submask = 1u << ((nodeId - 1) % 32);
            if (field >= TaxiMaskSize || !(sTaxiNodesMask[field] & submask))
                continue;
            changed = bot->m_taxi.SetTaximaskNode(nodeId) || changed;
        }
        return changed;
    }

    bool MaximizeAssignedGatheringSkills(Player* bot)
    {
        if (!directorConfig.GetConfigValue<bool>(DirectorConfigKey::ProfessionMaxGatheringSkills))
            return false;

        bool changed = false;
        for (uint16 const skillId : {uint16(SKILL_HERBALISM), uint16(SKILL_MINING), uint16(SKILL_SKINNING)})
        {
            if (!bot->GetPureSkillValue(skillId))
                continue;

            for (ProfessionRank const& rank : ProfessionRanks)
                if (rank.skillId == skillId && !bot->HasSpell(rank.spellId))
                {
                    bot->learnSpell(rank.spellId, false, true);
                    changed = true;
                }

            if (bot->GetPureSkillValue(skillId) != 450 || bot->GetPureMaxSkillValue(skillId) != 450)
            {
                bot->SetSkill(skillId, bot->GetSkillStep(skillId), 450, 450);
                changed = true;
            }
        }
        return changed;
    }

    void ProvisionPersonaRoutineCapabilities(Player* bot)
    {
        if (!_provisionedRoutineBots.insert(bot->GetGUID().GetCounter()).second)
            return;

        bool const taxiChanged = GrantAllFactionTaxiNodes(bot);
        bool const skillsChanged = MaximizeAssignedGatheringSkills(bot);
        bool const changed = taxiChanged || skillsChanged;
        if (changed)
        {
            bot->SaveToDB(false, false);
            LOG_INFO(
                "module.cadia-director",
                "Provisioned max assigned gathering skills and faction taxi network for {}",
                bot->GetName());
        }
    }

    void ProtectPersonaFromRandomBotEvents(Player* bot)
    {
        if (!sRandomPlayerbotMgr.IsRandomBot(bot))
            return;

        auto const now = std::chrono::steady_clock::now();
        auto const existing = _lastRandomProtection.find(bot->GetGUID().GetCounter());
        if (existing != _lastRandomProtection.end() && now - existing->second < std::chrono::minutes(1))
            return;

        sRandomPlayerbotMgr.SetValue(bot, "teleport", 1, "cadia_controlled_persona");
        sRandomPlayerbotMgr.SetValue(bot, "randomize", 1, "cadia_controlled_persona");
        _lastRandomProtection[bot->GetGUID().GetCounter()] = now;
    }

    std::string RoutineSummary(uint32 botGuid) const
    {
        auto materialTarget = _activeMaterialTargets.find(botGuid);
        if (materialTarget != _activeMaterialTargets.end())
            return Acore::StringFormat(
                "the {} kit: {} in {}",
                materialTarget->second.professionName,
                materialTarget->second.itemName,
                materialTarget->second.selectedZone);
        auto objective = _activeProfessionObjectives.find(botGuid);
        if (objective == _activeProfessionObjectives.end())
            return "the guild material-kit routine";
        return Acore::StringFormat(
            "{} gathering in {}",
            objective->second.profession,
            objective->second.selectedZone);
    }

    void ApplyRoutineStrategies(PlayerbotAI* botAI)
    {
        botAI->ChangeStrategy(
            "+travel,+grind,+gather,+loot,-follow,-stay,-passive",
            BOT_STATE_NON_COMBAT);
        botAI->SetNextCheckDelay(0);
    }

    void ReconcileGroupDuty(uint32 botGuid)
    {
        Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(botGuid));
        PlayerbotAI* botAI = bot ? sPlayerbotsMgr.GetPlayerbotAI(bot) : nullptr;
        if (!bot || !botAI)
            return;

        ProvisionPersonaRoutineCapabilities(bot);
        ProtectPersonaFromRandomBotEvents(bot);

        Group* group = bot->GetGroup();
        Player* master = botAI->HasGameClientMaster() ? botAI->GetMaster() : nullptr;
        if (group && !master)
        {
            Player* leader = ObjectAccessor::FindPlayer(group->GetLeaderGUID());
            if (leader && !sPlayerbotsMgr.GetPlayerbotAI(leader))
            {
                botAI->SetMaster(leader);
                master = leader;
            }
        }
        uint64 const groupGuid = group ? group->GetGUID().GetRawValue() : 0;
        uint32 const masterGuid = master ? master->GetGUID().GetCounter() : 0;
        GroupDutyState& state = _groupDutyStates[botGuid];

        if (!group || !master)
        {
            bool const justDroppedGroup = state.groupGuid != 0;
            state = GroupDutyState{};
            ApplyRoutineStrategies(botAI);
            PersistGroupDutyState(bot, state, justDroppedGroup ? "routine_resumed" : "routine_active");
            if (justDroppedGroup)
                _professionTimer = 0;
            return;
        }

        if (state.groupGuid != groupGuid || state.masterGuid != masterGuid)
        {
            state.mode = GroupDutyMode::AwaitingDecision;
            state.groupGuid = groupGuid;
            state.masterGuid = masterGuid;
            ApplyRoutineStrategies(botAI);
            bot->Whisper(
                Acore::StringFormat(
                    "I'm working on {}. Should I report to you now, or keep working?",
                    RoutineSummary(botGuid)),
                LANG_UNIVERSAL,
                master);
            PersistGroupDutyState(bot, state, "awaiting_group_decision");
            return;
        }

        if (state.mode == GroupDutyMode::AwaitingDecision ||
            state.mode == GroupDutyMode::RoutineWhileGrouped)
        {
            ApplyRoutineStrategies(botAI);
            PersistGroupDutyState(
                bot,
                state,
                state.mode == GroupDutyMode::AwaitingDecision ?
                    "awaiting_group_decision" : "routine_continuing");
        }
        else
            PersistGroupDutyState(bot, state, "group_duty_active");
    }

    void PollPersonaBindingsForSnapshots()
    {
        if (_snapshotQueryInFlight)
            return;

        _snapshotQueryInFlight = true;
        _queryProcessor.AddCallback(CharacterDatabase.AsyncQuery(
            "SELECT b.character_guid, c.online FROM synthetic_persona_bindings b "
            "JOIN characters c ON c.guid = b.character_guid "
            "WHERE LOWER(b.persona_name) IN ('lyra', 'celene', 'ray', 'browntown')").WithCallback(
            [this](QueryResult result)
            {
                _snapshotQueryInFlight = false;
                if (!result)
                    return;

                do
                {
                    Field* fields = result->Fetch();
                    uint32 const botGuid = fields[0].Get<uint32>();
                    if (!fields[1].Get<bool>())
                    {
                        sRandomPlayerbotMgr.AddPlayerBot(PlayerGuid(botGuid), 0);
                        continue;
                    }
                    ReconcileGroupDuty(botGuid);
                    CaptureBotState(botGuid);
                } while (result->NextRow());
            }));
    }

    void PollEconomyProfiles()
    {
        if (_economyQueryInFlight)
            return;

        _economyQueryInFlight = true;
        _queryProcessor.AddCallback(CharacterDatabase.AsyncQuery(
            "SELECT p.bot_guid, p.auto_list, p.auto_buy, p.auto_craft, "
            "p.minimum_reserve_copper, p.max_spend_per_cycle_copper, "
            "p.max_gold_gift_copper, p.max_owned_auctions "
            "FROM synthetic_economy_profiles p "
            "JOIN synthetic_persona_bindings b ON b.character_guid = p.bot_guid "
            "WHERE p.enabled = 1 "
            "AND LOWER(b.persona_name) IN ('lyra', 'celene', 'ray', 'browntown')").WithCallback(
            [this](QueryResult result)
            {
                _economyQueryInFlight = false;
                if (!result)
                    return;

                do
                {
                    Field* fields = result->Fetch();
                    EconomyProfile profile;
                    profile.botGuid = fields[0].Get<uint32>();
                    profile.autoList = fields[1].Get<bool>();
                    profile.autoBuy = fields[2].Get<bool>();
                    profile.autoCraft = fields[3].Get<bool>();
                    profile.minimumReserve = fields[4].Get<uint64>();
                    profile.maxSpendPerCycle = fields[5].Get<uint64>();
                    profile.maxGoldGift = fields[6].Get<uint64>();
                    profile.maxOwnedAuctions = fields[7].Get<uint16>();
                    _economyProfiles[profile.botGuid] = profile;

                    Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(profile.botGuid));
                    PlayerbotAI* botAI = bot ? sPlayerbotsMgr.GetPlayerbotAI(bot) : nullptr;
                    if (!bot || !botAI || bot->isDead() || bot->IsInCombat() || botAI->HasGameClientMaster())
                        continue;

                    RunEconomyCycle(bot, botAI, true, Event("cadia economy", "", bot));
                } while (result->NextRow());
            }));
    }

    void UpdateProfessionObjective(
        ProfessionObjective const& objective,
        std::string const& status,
        std::string const& resultCode,
        uint16 observedSkill,
        bool completed = false)
    {
        CharacterDatabase.Execute(Acore::StringFormat(
            "UPDATE synthetic_profession_objectives SET status = '{}', last_result_code = '{}', "
            "last_observed_skill = {}{} WHERE id = {}",
            status,
            resultCode,
            observedSkill,
            completed ? ", completed_at = CURRENT_TIMESTAMP" : "",
            objective.id));
    }

    void RecordProfessionResult(
        ProfessionObjective const& objective,
        Player* bot,
        std::string const& actionKind,
        std::string const& resultCode,
        uint16 skillBefore,
        uint16 skillAfter,
        uint32 itemEntry = 0,
        uint32 itemCount = 0)
    {
        CharacterDatabase.Execute(Acore::StringFormat(
            "INSERT INTO synthetic_profession_ledger "
            "(plan_id, objective_id, bot_guid, bot_name, profession, action_kind, "
            "item_entry, item_count, skill_before, skill_after, result_code) "
            "VALUES ({}, {}, {}, '{}', '{}', '{}', {}, {}, {}, {}, '{}')",
            objective.planId,
            objective.id,
            objective.botGuid,
            bot->GetName(),
            objective.profession,
            actionKind,
            itemEntry,
            itemCount,
            skillBefore,
            skillAfter,
            resultCode));
    }

    bool IsProfessionMaterial(Item* item, std::string const& category) const
    {
        if (!item || item->IsSoulBound() || !item->CanBeTraded() || item->IsInTrade() ||
            item->IsNotEmptyBag() || item->GetTemplate()->HasFlag(ITEM_FLAG_CONJURED))
            return false;

        ItemTemplate const* itemTemplate = item->GetTemplate();
        if (category == "mining")
        {
            if (itemTemplate->Class == ITEM_CLASS_GEM)
                return true;
            return itemTemplate->Class == ITEM_CLASS_TRADE_GOODS &&
                (itemTemplate->SubClass == ITEM_SUBCLASS_METAL_STONE ||
                    itemTemplate->SubClass == ITEM_SUBCLASS_ELEMENTAL);
        }
        if (category == "herbalism")
            return itemTemplate->Class == ITEM_CLASS_TRADE_GOODS &&
                itemTemplate->SubClass == ITEM_SUBCLASS_HERB;
        if (category == "skinning")
            return itemTemplate->Class == ITEM_CLASS_TRADE_GOODS &&
                itemTemplate->SubClass == ITEM_SUBCLASS_LEATHER;
        return false;
    }

    Item* SelectProfessionMaterial(Player* bot, std::string const& category) const
    {
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            if (Item* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                if (IsProfessionMaterial(item, category))
                    return item;

        for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        {
            Bag* bag = bot->GetBagByPos(bagSlot);
            if (!bag)
                continue;
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                if (Item* item = bag->GetItemByPos(slot))
                    if (IsProfessionMaterial(item, category))
                        return item;
        }
        return nullptr;
    }

    ProfessionDepositResult DepositOneProfessionMaterial(
        ProfessionObjective const& objective,
        Player* bot)
    {
        Item* item = SelectProfessionMaterial(bot, objective.depositCategory);
        if (!item)
            return ProfessionDepositResult::NoMaterial;

        Guild* guild = sGuildMgr->GetGuildById(bot->GetGuildId());
        if (!guild)
            return ProfessionDepositResult::NoGuild;
        if (!guild->MemberHasTabRights(
                bot->GetGUID(), objective.guildBankTab, GUILD_BANK_RIGHT_DEPOSIT_ITEM))
            return ProfessionDepositResult::NoRights;

        uint32 const itemEntry = item->GetEntry();
        uint32 const itemCount = item->GetCount();
        ObjectGuid const itemGuid = item->GetGUID();
        uint8 const bagSlot = item->GetBagSlot();
        uint8 const itemSlot = item->GetSlot();
        guild->SwapItemsWithInventory(
            bot,
            false,
            objective.guildBankTab,
            NULL_SLOT,
            bagSlot,
            itemSlot,
            0);

        if (bot->GetItemByGuid(itemGuid))
            return ProfessionDepositResult::BankFull;

        uint16 const skill = bot->GetPureSkillValue(objective.skillId);
        RecordProfessionResult(
            objective, bot, "GUILD_BANK_DEPOSIT", "material_deposited", skill, skill, itemEntry, itemCount);
        LOG_INFO(
            "module.cadia-director",
            "{} deposited profession material {} x{} into guild-bank tab {}",
            bot->GetName(),
            itemEntry,
            itemCount,
            objective.guildBankTab);
        return ProfessionDepositResult::Deposited;
    }

    void ExecuteDepositGuildBank(uint64 intentId, Player* bot)
    {
        if (bot->IsInCombat())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "in_combat");
            return;
        }

        uint32 const botGuid = bot->GetGUID().GetCounter();
        std::string const query = Acore::StringFormat(
            "SELECT o.id, o.plan_id, o.bot_guid, o.profession, o.skill_id, o.stage_order, "
            "o.skill_from, o.skill_to, o.min_character_level, o.selected_zone, "
            "o.selected_zone_id, o.tool_item_id, o.deposit_category, o.guild_bank_tab, "
            "o.deposit_free_slots FROM synthetic_profession_objectives o "
            "JOIN synthetic_profession_plans p ON p.id = o.plan_id "
            "WHERE p.status = 'active' AND o.bot_guid = {} AND o.status IN "
            "('queued', 'active', 'waiting', 'depositing') "
            "ORDER BY o.skill_id, o.stage_order",
            botGuid);

        _queryProcessor.AddCallback(CharacterDatabase.AsyncQuery(query).WithCallback(
            [this, intentId, botGuid](QueryResult result)
            {
                CompleteDepositGuildBank(intentId, botGuid, result);
            }));
    }

    void CompleteDepositGuildBank(uint64 intentId, uint32 botGuid, QueryResult result)
    {
        Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(botGuid));
        if (!bot)
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "bot_offline");
            return;
        }
        if (bot->isDead())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "bot_dead");
            return;
        }
        if (bot->IsInCombat())
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "in_combat");
            return;
        }
        if (!result)
        {
            SetIntentStatus(intentId, IntentStatus::Rejected, "profession_objective_missing");
            return;
        }

        bool deposited = false;
        bool bankFull = false;
        bool noGuild = false;
        bool noRights = false;
        std::unordered_set<std::string> handledCategories;
        do
        {
            ProfessionObjective const objective = ReadProfessionObjective(result->Fetch());
            if (!handledCategories.insert(objective.depositCategory).second)
                continue;

            for (uint16 stack = 0; stack < 256; ++stack)
            {
                ProfessionDepositResult const depositResult = DepositOneProfessionMaterial(objective, bot);
                if (depositResult == ProfessionDepositResult::Deposited)
                {
                    deposited = true;
                    continue;
                }
                if (depositResult == ProfessionDepositResult::BankFull)
                    bankFull = true;
                else if (depositResult == ProfessionDepositResult::NoGuild)
                    noGuild = true;
                else if (depositResult == ProfessionDepositResult::NoRights)
                    noRights = true;
                break;
            }
        } while (result->NextRow());

        if (deposited)
        {
            SetIntentStatus(
                intentId,
                IntentStatus::Succeeded,
                bankFull ? "guild_bank_deposit_partial" : "guild_bank_deposited");
            return;
        }
        if (noGuild)
            SetIntentStatus(intentId, IntentStatus::Rejected, "guild_bank_unavailable");
        else if (noRights)
            SetIntentStatus(intentId, IntentStatus::Rejected, "guild_bank_rights_missing");
        else if (bankFull)
            SetIntentStatus(intentId, IntentStatus::Rejected, "guild_bank_full");
        else
            SetIntentStatus(intentId, IntentStatus::Succeeded, "guild_bank_nothing_to_deposit");
    }

    ProfessionObjective ReadProfessionObjective(Field* fields) const
    {
        ProfessionObjective objective;
        objective.id = fields[0].Get<uint64>();
        objective.planId = fields[1].Get<uint64>();
        objective.botGuid = fields[2].Get<uint32>();
        objective.profession = fields[3].Get<std::string>();
        objective.skillId = fields[4].Get<uint16>();
        objective.stageOrder = fields[5].Get<uint8>();
        objective.skillFrom = fields[6].Get<uint16>();
        objective.skillTo = fields[7].Get<uint16>();
        objective.minCharacterLevel = fields[8].Get<uint8>();
        objective.selectedZone = fields[9].Get<std::string>();
        objective.selectedZoneId = fields[10].Get<uint32>();
        objective.toolItemId = fields[11].Get<uint32>();
        objective.depositCategory = fields[12].Get<std::string>();
        objective.guildBankTab = fields[13].Get<uint8>();
        objective.depositFreeSlots = fields[14].Get<uint8>();
        return objective;
    }

    bool EnsureProfessionTool(ProfessionObjective const& objective, Player* bot)
    {
        if (!objective.toolItemId || bot->HasItemCount(objective.toolItemId, 1))
            return true;
        if (!directorConfig.GetConfigValue<bool>(DirectorConfigKey::ProfessionProvisionTools))
            return false;
        if (!bot->StoreNewItemInBestSlots(objective.toolItemId, 1))
            return false;

        uint16 const skill = bot->GetPureSkillValue(objective.skillId);
        RecordProfessionResult(
            objective,
            bot,
            "TOOL_PROVISION",
            "profession_tool_provisioned",
            skill,
            skill,
            objective.toolItemId,
            1);
        return true;
    }

    bool TryTrainProfessionRank(ProfessionObjective const& objective, Player* bot)
    {
        if (!directorConfig.GetConfigValue<bool>(DirectorConfigKey::ProfessionAutoTrainRanks))
            return false;

        uint16 const currentSkill = bot->GetPureSkillValue(objective.skillId);
        uint16 const currentCap = bot->GetPureMaxSkillValue(objective.skillId);
        for (ProfessionRank const& rank : ProfessionRanks)
        {
            if (rank.skillId != objective.skillId || rank.newCap <= currentCap ||
                currentSkill < rank.requiredSkill || bot->GetLevel() < rank.requiredLevel)
                continue;

            if (!bot->HasSpell(rank.spellId))
                bot->learnSpell(rank.spellId, false);
            if (bot->GetPureMaxSkillValue(objective.skillId) < rank.newCap)
                bot->SetSkill(
                    objective.skillId,
                    bot->GetSkillStep(objective.skillId),
                    currentSkill,
                    rank.newCap);

            uint16 const trainedCap = bot->GetPureMaxSkillValue(objective.skillId);
            bool const trained = trainedCap >= rank.newCap;
            RecordProfessionResult(
                objective,
                bot,
                "TRAIN_RANK",
                trained ? "profession_rank_trained" : "profession_rank_training_failed",
                currentSkill,
                currentSkill);
            return trained;
        }
        return false;
    }

    uint16 GetGatheringNodeRequiredSkill(uint32 gameObjectEntry, uint16 skillId) const
    {
        GameObjectTemplate const* gameObjectTemplate = sObjectMgr->GetGameObjectTemplate(gameObjectEntry);
        if (!gameObjectTemplate)
            return 0;

        LockEntry const* lock = sLockStore.LookupEntry(gameObjectTemplate->GetLockId());
        if (!lock)
            return 0;

        for (uint8 index = 0; index < 8; ++index)
            if (lock->Type[index] == LOCK_KEY_SKILL &&
                SkillByLockType(LockType(lock->Index[index])) == skillId)
                return std::max<uint16>(1, lock->Skill[index]);

        return 0;
    }

    ProfessionTravelDestination* CreateProfessionTravelDestination(
        ProfessionObjective const& objective,
        Player* bot,
        uint16 currentSkill)
    {
        struct Anchor
        {
            int32 entry = 0;
            uint32 mapId = 0;
            float x = 0.0f;
            float y = 0.0f;
            float z = 0.0f;
            uint16 requiredSkill = 0;
            std::string title;
        } best;

        if (objective.skillId == SKILL_MINING || objective.skillId == SKILL_HERBALISM)
        {
            QueryResult spawns = WorldDatabase.Query(Acore::StringFormat(
                "SELECT id, map, position_x, position_y, position_z FROM gameobject "
                "WHERE zoneId = {} ORDER BY guid",
                objective.selectedZoneId));
            if (spawns)
            {
                do
                {
                    Field* fields = spawns->Fetch();
                    uint32 const entry = fields[0].Get<uint32>();
                    uint16 const requiredSkill =
                        GetGatheringNodeRequiredSkill(entry, objective.skillId);
                    if (!requiredSkill || requiredSkill > currentSkill || requiredSkill < best.requiredSkill)
                        continue;

                    GameObjectTemplate const* gameObjectTemplate = sObjectMgr->GetGameObjectTemplate(entry);
                    best.entry = -static_cast<int32>(entry);
                    best.mapId = fields[1].Get<uint32>();
                    best.x = fields[2].Get<float>();
                    best.y = fields[3].Get<float>();
                    best.z = fields[4].Get<float>();
                    best.requiredSkill = requiredSkill;
                    best.title = gameObjectTemplate ? gameObjectTemplate->name : objective.selectedZone;
                } while (spawns->NextRow());
            }
        }
        else if (objective.skillId == SKILL_SKINNING)
        {
            QueryResult spawns = WorldDatabase.Query(Acore::StringFormat(
                "SELECT c.id, c.map, c.position_x, c.position_y, c.position_z, ct.maxlevel "
                "FROM creature c JOIN creature_template ct ON ct.entry = c.id "
                "WHERE c.zoneId = {} AND ct.skinloot <> 0 ORDER BY ct.maxlevel DESC, c.guid",
                objective.selectedZoneId));
            if (spawns)
            {
                do
                {
                    Field* fields = spawns->Fetch();
                    uint32 const entry = fields[0].Get<uint32>();
                    CreatureTemplate const* creatureTemplate = sObjectMgr->GetCreatureTemplate(entry);
                    if (!creatureTemplate || creatureTemplate->GetRequiredLootSkill() != SKILL_SKINNING)
                        continue;

                    uint16 const creatureLevel = fields[5].Get<uint16>();
                    uint16 const requiredSkill = creatureLevel < 10 ? 1 :
                        creatureLevel < 20 ? (creatureLevel - 10) * 10 : creatureLevel * 5;
                    if (requiredSkill > currentSkill || requiredSkill < best.requiredSkill)
                        continue;

                    best.entry = static_cast<int32>(entry);
                    best.mapId = fields[1].Get<uint32>();
                    best.x = fields[2].Get<float>();
                    best.y = fields[3].Get<float>();
                    best.z = fields[4].Get<float>();
                    best.requiredSkill = requiredSkill;
                    best.title = creatureTemplate->Name;
                } while (spawns->NextRow());
            }
        }

        if (!best.mapId && best.x == 0.0f && best.y == 0.0f)
            return nullptr;

        auto destination = std::make_unique<ProfessionTravelDestination>(
            objective.id,
            objective.selectedZoneId,
            best.requiredSkill,
            best.entry,
            best.mapId,
            best.x,
            best.y,
            best.z,
            Acore::StringFormat("{} objective in {}", best.title, objective.selectedZone));
        ProfessionTravelDestination* result = destination.get();
        _professionDestinationStorage.push_back(std::move(destination));
        _professionDestinations[objective.id] = result;
        _professionDestinationRefreshSkill[objective.id] = currentSkill + 25;
        LOG_INFO(
            "module.cadia-director",
            "Created native profession route for {} {} to {} in {} (required skill {})",
            bot->GetName(),
            objective.profession,
            best.title,
            objective.selectedZone,
            best.requiredSkill);
        return result;
    }

    ProfessionTravelDestination* GetProfessionTravelDestination(
        ProfessionObjective const& objective,
        Player* bot,
        uint16 currentSkill)
    {
        auto existing = _professionDestinations.find(objective.id);
        auto refreshSkill = _professionDestinationRefreshSkill.find(objective.id);
        if (existing != _professionDestinations.end() &&
            refreshSkill != _professionDestinationRefreshSkill.end() &&
            currentSkill < refreshSkill->second)
            return existing->second;

        return CreateProfessionTravelDestination(objective, bot, currentSkill);
    }

    bool QueueNearbyProfessionNode(
        ProfessionObjective const& objective,
        Player* bot,
        PlayerbotAI* botAI)
    {
        if (objective.skillId != SKILL_MINING && objective.skillId != SKILL_HERBALISM)
            return false;

        std::list<GameObject*> gameObjects;
        float constexpr searchRange = 300.0f;
        AnyGameObjectInObjectRangeCheck check(bot, searchRange);
        Acore::GameObjectListSearcher<AnyGameObjectInObjectRangeCheck> searcher(bot, gameObjects, check);
        Cell::VisitObjects(bot, searcher, searchRange);

        GameObject* nearest = nullptr;
        float nearestDistance = std::numeric_limits<float>::max();
        uint16 nearestRequiredSkill = 0;
        for (GameObject* gameObject : gameObjects)
        {
            if (!gameObject || !gameObject->isSpawned() || gameObject->GetGoState() != GO_STATE_READY)
                continue;

            uint16 const requiredSkill =
                GetGatheringNodeRequiredSkill(gameObject->GetEntry(), objective.skillId);
            if (!requiredSkill || requiredSkill > bot->GetSkillValue(objective.skillId))
                continue;

            float const distance = bot->GetDistance(gameObject);
            if (distance >= nearestDistance)
                continue;
            nearest = gameObject;
            nearestDistance = distance;
            nearestRequiredSkill = requiredSkill;
        }

        if (!nearest)
            return false;

        if (nearestDistance > sPlayerbotAIConfig.lootDistance)
        {
            TravelTarget* target =
                botAI->GetAiObjectContext()->GetValue<TravelTarget*>("travel target")->Get();
            if (target && target->isActive() && target->getPosition())
            {
                float const dx = target->getPosition()->GetPositionX() - nearest->GetPositionX();
                float const dy = target->getPosition()->GetPositionY() - nearest->GetPositionY();
                if (target->getPosition()->GetMapId() == nearest->GetMapId() && dx * dx + dy * dy < 1.0f)
                    return true;
            }

            GameObjectTemplate const* gameObjectTemplate = nearest->GetGOInfo();
            auto destination = std::make_unique<ProfessionTravelDestination>(
                objective.id,
                objective.selectedZoneId,
                nearestRequiredSkill,
                -static_cast<int32>(nearest->GetEntry()),
                nearest->GetMapId(),
                nearest->GetPositionX(),
                nearest->GetPositionY(),
                nearest->GetPositionZ(),
                Acore::StringFormat(
                    "active {} in {}",
                    gameObjectTemplate ? gameObjectTemplate->name : objective.profession,
                    objective.selectedZone));
            ProfessionTravelDestination* activeDestination = destination.get();
            _professionDestinationStorage.push_back(std::move(destination));

            std::vector<WorldPosition*> points = activeDestination->getPoints(true);
            if (!target || points.empty())
                return false;
            target->setTarget(activeDestination, points.front());
            target->setForced(true);
            botAI->SetNextCheckDelay(0);
            return true;
        }

        Event const nodeEvent("cadia profession gather", nearest->GetGUID(), bot);
        botAI->DoSpecificAction("add loot", nodeEvent, true);
        bool const selected = botAI->DoSpecificAction("loot", Event(), true);
        if (!selected)
            return false;

        bool const opened = nearestDistance <= INTERACTION_DISTANCE - 2.0f ?
            botAI->DoSpecificAction("open loot", Event(), true) :
            botAI->DoSpecificAction("move to loot", Event(), true);
        if (opened)
            botAI->SetNextCheckDelay(0);
        return opened;
    }

    bool SetProfessionTravelTarget(
        ProfessionObjective const& objective,
        Player* bot,
        PlayerbotAI* botAI)
    {
        TravelTarget* target = botAI->GetAiObjectContext()->GetValue<TravelTarget*>("travel target")->Get();

        auto destinationZoneId = [](TravelDestination* destination) -> uint32
        {
            if (auto* profession = dynamic_cast<ProfessionTravelDestination*>(destination))
                return profession->GetZoneId();
            auto* explore = dynamic_cast<ExploreTravelDestination*>(destination);
            AreaTableEntry const* area = explore ? sAreaTableStore.LookupEntry(explore->getAreaId()) : nullptr;
            if (!area && destination)
            {
                std::vector<WorldPosition*> points = destination->getPoints(true);
                if (!points.empty())
                    area = points.front()->getArea();
            }
            if (!area)
                return 0;

            uint32 zoneId = area->ID;
            while (area && area->zone)
            {
                zoneId = area->zone;
                area = sAreaTableStore.LookupEntry(zoneId);
            }
            return zoneId;
        };

        if (bot->GetZoneId() == objective.selectedZoneId ||
            (target && target->isActive() && target->getDestination() &&
                destinationZoneId(target->getDestination()) == objective.selectedZoneId))
        {
            botAI->ChangeStrategy("+travel,+grind,+gather,+loot,-follow,-stay,-passive", BOT_STATE_NON_COMBAT);
            QueueNearbyProfessionNode(objective, bot, botAI);
            botAI->SetNextCheckDelay(0);
            return true;
        }

        TravelDestination* destination = nullptr;
        WorldPosition botPosition(bot);
        for (TravelDestination* candidate :
            TravelMgr::instance().getExploreTravelDestinations(bot, true, true))
        {
            if (destinationZoneId(candidate) != objective.selectedZoneId)
                continue;
            if (!destination || candidate->distanceTo(&botPosition) < destination->distanceTo(&botPosition))
                destination = candidate;
        }
        if (!destination)
            for (TravelDestination* candidate :
                TravelMgr::instance().getGrindTravelDestinations(bot, true, true, 0))
            {
                if (destinationZoneId(candidate) != objective.selectedZoneId)
                    continue;
                if (!destination || candidate->distanceTo(&botPosition) < destination->distanceTo(&botPosition))
                    destination = candidate;
            }
        if (!destination)
            if (auto alias = ProfessionTravelAliases.find(objective.selectedZoneId);
                alias != ProfessionTravelAliases.end())
                destination = ChooseTravelTargetAction::FindDestination(
                    bot, alias->second, true, false, false, false, false);
        if (!destination)
            destination = GetProfessionTravelDestination(
                objective, bot, bot->GetPureSkillValue(objective.skillId));
        if (!destination || !target)
        {
            uint64 const unavailableKey =
                (static_cast<uint64>(objective.botGuid) << 32) | objective.selectedZoneId;
            if (_unavailableProfessionZones.insert(unavailableKey).second)
                LOG_WARN(
                    "module.cadia-director",
                    "No profession travel destination for {} zone {} ({}) across {} explore destinations",
                    bot->GetName(),
                    objective.selectedZone,
                    objective.selectedZoneId,
                    TravelMgr::instance().getExploreTravelDestinations(bot, true, true).size());
            return false;
        }

        std::vector<WorldPosition*> points = destination->nextPoint(&botPosition, true);
        if (points.empty())
            return false;

        // The Playerbots cross-map movement branch is disabled in this fork.
        // Use a narrowly scoped work teleport only to the allowlisted objective
        // anchor. This grants no GM rank and can never target an arbitrary point.
        if (bot->GetMapId() != points.front()->GetMapId())
        {
            bool const teleported = bot->TeleportTo(
                points.front()->GetMapId(),
                points.front()->GetPositionX(),
                points.front()->GetPositionY(),
                points.front()->GetPositionZ(),
                points.front()->GetOrientation());
            if (teleported)
                botAI->SetNextCheckDelay(0);
            return teleported;
        }

        target->setTarget(destination, points.front());
        target->setForced(true);
        botAI->ChangeStrategy("+travel,+grind,+gather,+loot,-follow,-stay,-passive", BOT_STATE_NON_COMBAT);
        botAI->SetNextCheckDelay(0);
        return true;
    }

    void UpdateMaterialKitTarget(
        MaterialKitTarget const& target,
        std::string const& status,
        std::string const& resultCode,
        uint32 observedBankCount,
        bool completed = false)
    {
        CharacterDatabase.Execute(Acore::StringFormat(
            "UPDATE synthetic_material_kit_targets SET status = '{}', last_result_code = '{}', "
            "observed_bank_count = {}{} WHERE id = {}",
            status,
            resultCode,
            observedBankCount,
            completed ? ", completed_at = CURRENT_TIMESTAMP" : "",
            target.id));
    }

    void RecordMaterialKitResult(
        MaterialKitTarget const& target,
        Player* bot,
        std::string const& actionKind,
        std::string const& resultCode,
        uint32 itemCount)
    {
        CharacterDatabase.Execute(Acore::StringFormat(
            "INSERT INTO synthetic_material_kit_ledger "
            "(plan_id, target_id, bot_guid, bot_name, action_kind, item_entry, item_count, "
            "observed_bank_count, result_code) VALUES ({}, {}, {}, '{}', '{}', {}, {}, {}, '{}')",
            target.planId,
            target.id,
            target.botGuid,
            bot->GetName(),
            actionKind,
            target.itemEntry,
            itemCount,
            target.observedBankCount,
            resultCode));
    }

    ProfessionDepositResult DepositMaterialKitItem(MaterialKitTarget const& target, Player* bot)
    {
        Item* item = bot->GetItemByEntry(target.itemEntry);
        if (!item || item->IsSoulBound() || !item->CanBeTraded() || item->IsInTrade())
            return ProfessionDepositResult::NoMaterial;

        Guild* guild = sGuildMgr->GetGuildById(bot->GetGuildId());
        if (!guild || bot->GetGuildId() != target.guildId)
            return ProfessionDepositResult::NoGuild;
        if (!guild->MemberHasTabRights(
                bot->GetGUID(), target.guildBankTab, GUILD_BANK_RIGHT_DEPOSIT_ITEM))
            return ProfessionDepositResult::NoRights;

        uint32 const count = item->GetCount();
        ObjectGuid const itemGuid = item->GetGUID();
        guild->SwapItemsWithInventory(
            bot,
            false,
            target.guildBankTab,
            NULL_SLOT,
            item->GetBagSlot(),
            item->GetSlot(),
            0);
        if (bot->GetItemByGuid(itemGuid))
            return ProfessionDepositResult::BankFull;

        RecordMaterialKitResult(target, bot, "GUILD_BANK_DEPOSIT", "material_deposited", count);
        return ProfessionDepositResult::Deposited;
    }

    ProfessionObjective MaterialTargetAsObjective(MaterialKitTarget const& target) const
    {
        ProfessionObjective objective;
        objective.id = target.id;
        objective.planId = target.planId;
        objective.botGuid = target.botGuid;
        objective.skillId = target.gatheringSkillId;
        objective.skillFrom = 1;
        objective.skillTo = 451;
        objective.minCharacterLevel = target.minCharacterLevel;
        objective.profession = target.professionName;
        objective.selectedZone = target.selectedZone;
        objective.selectedZoneId = target.selectedZoneId;
        objective.toolItemId = target.gatheringSkillId == SKILL_MINING ? 2901 :
            (target.gatheringSkillId == SKILL_SKINNING ? 7005 : 0);
        objective.depositCategory = target.depositCategory;
        objective.guildBankTab = target.guildBankTab;
        return objective;
    }

    void ProcessMaterialKitTarget(MaterialKitTarget const& target)
    {
        if (target.observedBankCount >= target.bankThreshold)
        {
            UpdateMaterialKitTarget(target, "completed", "bank_threshold_met", target.observedBankCount, true);
            return;
        }

        Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(target.botGuid));
        PlayerbotAI* botAI = bot ? sPlayerbotsMgr.GetPlayerbotAI(bot) : nullptr;
        if (!bot || !botAI)
        {
            UpdateMaterialKitTarget(target, "waiting", "bot_offline", target.observedBankCount);
            return;
        }

        _activeMaterialTargets[target.botGuid] = target;
        ProvisionPersonaRoutineCapabilities(bot);
        if (bot->GetLevel() < target.minCharacterLevel)
        {
            UpdateMaterialKitTarget(
                target, "waiting", "waiting_for_character_level", target.observedBankCount);
            return;
        }
        if (bot->isDead() || bot->IsInCombat())
        {
            UpdateMaterialKitTarget(
                target,
                "waiting",
                bot->isDead() ? "bot_dead" : "in_combat",
                target.observedBankCount);
            return;
        }

        auto const duty = _groupDutyStates.find(target.botGuid);
        if (botAI->HasGameClientMaster() && duty != _groupDutyStates.end() &&
            duty->second.mode == GroupDutyMode::Reporting)
        {
            UpdateMaterialKitTarget(target, "waiting", "group_duty_active", target.observedBankCount);
            return;
        }
        if (target.acquisitionMode == "auction")
        {
            UpdateMaterialKitTarget(
                target, "waiting", "auction_procurement_required", target.observedBankCount);
            return;
        }
        if (target.gatheringSkillId && !bot->GetPureSkillValue(target.gatheringSkillId))
        {
            UpdateMaterialKitTarget(
                target, "waiting", "assigned_gathering_skill_missing", target.observedBankCount);
            return;
        }

        ProfessionDepositResult const deposit = DepositMaterialKitItem(target, bot);
        if (deposit == ProfessionDepositResult::Deposited)
        {
            UpdateMaterialKitTarget(target, "depositing", "material_deposited", target.observedBankCount);
            return;
        }
        if (deposit == ProfessionDepositResult::NoRights)
        {
            UpdateMaterialKitTarget(target, "waiting", "guild_bank_rights_missing", target.observedBankCount);
            return;
        }
        if (deposit == ProfessionDepositResult::NoGuild)
        {
            UpdateMaterialKitTarget(target, "waiting", "guild_bank_unavailable", target.observedBankCount);
            return;
        }
        if (deposit == ProfessionDepositResult::BankFull)
        {
            UpdateMaterialKitTarget(target, "waiting", "guild_bank_full", target.observedBankCount);
            return;
        }

        ProfessionObjective const objective = MaterialTargetAsObjective(target);
        if (objective.toolItemId && !EnsureProfessionTool(objective, bot))
        {
            UpdateMaterialKitTarget(target, "waiting", "profession_tool_missing", target.observedBankCount);
            return;
        }

        bool const routed = SetProfessionTravelTarget(objective, bot, botAI);
        UpdateMaterialKitTarget(
            target,
            routed ? "active" : "waiting",
            routed ? (bot->GetZoneId() == target.selectedZoneId ?
                "gathering_for_material_kit" : "traveling_for_material_kit") :
                "material_zone_unavailable",
            target.observedBankCount);
    }

    void ProcessMaterialKitTargetRows(QueryResult result)
    {
        if (!result)
            return;

        std::unordered_set<uint32> selectedBots;
        do
        {
            Field* fields = result->Fetch();
            MaterialKitTarget target;
            target.id = fields[0].Get<uint64>();
            target.planId = fields[1].Get<uint64>();
            target.botGuid = fields[2].Get<uint32>();
            target.professionName = fields[3].Get<std::string>();
            target.itemEntry = fields[4].Get<uint32>();
            target.itemName = fields[5].Get<std::string>();
            target.requiredCount = fields[6].Get<uint32>();
            target.bankThreshold = fields[7].Get<uint32>();
            target.gatheringSkillId = fields[8].Get<uint16>();
            target.acquisitionMode = fields[9].Get<std::string>();
            target.depositCategory = fields[10].Get<std::string>();
            target.selectedZone = fields[11].Get<std::string>();
            target.selectedZoneId = fields[12].Get<uint32>();
            target.minCharacterLevel = fields[13].Get<uint8>();
            target.guildId = fields[14].Get<uint32>();
            target.guildBankTab = fields[15].Get<uint8>();
            target.observedBankCount = fields[16].Get<uint32>();
            if (!selectedBots.insert(target.botGuid).second)
                continue;
            ProcessMaterialKitTarget(target);
        } while (result->NextRow());
    }

    void PollMaterialKitTargets()
    {
        if (_materialKitQueryInFlight)
            return;

        _materialKitQueryInFlight = true;
        _queryProcessor.AddCallback(CharacterDatabase.AsyncQuery(
            "SELECT t.id, t.plan_id, t.bot_guid, t.profession_name, t.item_entry, t.item_name, "
            "t.required_count, t.bank_threshold, t.gathering_skill_id, t.acquisition_mode, "
            "t.deposit_category, t.selected_zone, t.selected_zone_id, t.min_character_level, "
            "t.guild_id, t.guild_bank_tab, COALESCE((SELECT SUM(ii.count) FROM guild_bank_item gbi "
            "JOIN item_instance ii ON ii.guid = gbi.item_guid WHERE gbi.guildid = t.guild_id "
            "AND ii.itemEntry = t.item_entry), 0) AS bank_count "
            "FROM synthetic_material_kit_targets t "
            "JOIN synthetic_material_kit_plans p ON p.id = t.plan_id "
            "JOIN characters c ON c.guid = t.bot_guid "
            "JOIN synthetic_persona_bindings b ON b.character_guid = t.bot_guid "
            "WHERE p.status = 'active' AND t.status IN ('queued','active','waiting','depositing') "
            "AND LOWER(b.persona_name) IN ('lyra','celene','ray','browntown') "
            "ORDER BY t.bot_guid, "
            "CASE WHEN t.min_character_level <= c.level AND t.acquisition_mode <> 'auction' THEN 0 ELSE 1 END, "
            "t.id").WithCallback(
            [this](QueryResult result)
            {
                _materialKitQueryInFlight = false;
                ProcessMaterialKitTargetRows(result);
            }));
    }

    void ProcessProfessionObjective(ProfessionObjective const& objective)
    {
        Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(objective.botGuid));
        PlayerbotAI* botAI = bot ? sPlayerbotsMgr.GetPlayerbotAI(bot) : nullptr;
        if (!bot || !botAI)
        {
            UpdateProfessionObjective(objective, "waiting", "bot_offline", 0);
            return;
        }

        _activeProfessionObjectives[objective.botGuid] = objective;
        ProvisionPersonaRoutineCapabilities(bot);

        uint16 const currentSkill = bot->GetPureSkillValue(objective.skillId);
        if (!currentSkill)
        {
            UpdateProfessionObjective(objective, "waiting", "profession_not_learned", 0);
            return;
        }
        if (bot->isDead() || bot->IsInCombat())
        {
            UpdateProfessionObjective(objective, "waiting", bot->isDead() ? "bot_dead" : "in_combat", currentSkill);
            return;
        }

        auto const duty = _groupDutyStates.find(objective.botGuid);
        if (botAI->HasGameClientMaster() && duty != _groupDutyStates.end() &&
            duty->second.mode == GroupDutyMode::Reporting)
        {
            botAI->ChangeStrategy("-travel,-grind,+gather,+loot", BOT_STATE_NON_COMBAT);
            botAI->SetNextCheckDelay(0);
            UpdateProfessionObjective(objective, "active", "party_gathering", currentSkill);
            return;
        }

        if (currentSkill >= objective.skillTo)
        {
            ProfessionDepositResult const deposit = DepositOneProfessionMaterial(objective, bot);
            if (deposit == ProfessionDepositResult::Deposited)
                UpdateProfessionObjective(objective, "depositing", "material_deposited", currentSkill);
            else if (deposit == ProfessionDepositResult::NoMaterial)
            {
                UpdateProfessionObjective(objective, "completed", "stage_complete", currentSkill, true);
                RecordProfessionResult(
                    objective, bot, "STAGE_COMPLETE", "stage_complete", currentSkill, currentSkill);
            }
            else if (deposit == ProfessionDepositResult::NoRights)
                UpdateProfessionObjective(objective, "waiting", "guild_bank_rights_missing", currentSkill);
            else if (deposit == ProfessionDepositResult::BankFull)
                UpdateProfessionObjective(objective, "waiting", "guild_bank_full", currentSkill);
            else
                UpdateProfessionObjective(objective, "waiting", "guild_bank_unavailable", currentSkill);
            return;
        }

        if (currentSkill < objective.skillFrom)
        {
            UpdateProfessionObjective(objective, "queued", "waiting_for_prior_stage", currentSkill);
            return;
        }
        if (bot->GetLevel() < objective.minCharacterLevel)
        {
            botAI->ChangeStrategy("-travel,-grind,+gather,+loot", BOT_STATE_NON_COMBAT);
            UpdateProfessionObjective(objective, "waiting", "waiting_for_character_level", currentSkill);
            return;
        }

        if (currentSkill >= bot->GetPureMaxSkillValue(objective.skillId))
        {
            if (!TryTrainProfessionRank(objective, bot))
            {
                UpdateProfessionObjective(objective, "waiting", "profession_rank_training_blocked", currentSkill);
                return;
            }
        }
        if (!EnsureProfessionTool(objective, bot))
        {
            UpdateProfessionObjective(objective, "waiting", "profession_tool_missing", currentSkill);
            return;
        }

        if (SelectProfessionMaterial(bot, objective.depositCategory))
        {
            ProfessionDepositResult const deposit = DepositOneProfessionMaterial(objective, bot);
            if (deposit == ProfessionDepositResult::Deposited)
            {
                UpdateProfessionObjective(objective, "active", "material_deposited", currentSkill);
                return;
            }
            if (deposit == ProfessionDepositResult::NoRights)
            {
                UpdateProfessionObjective(objective, "waiting", "guild_bank_rights_missing", currentSkill);
                return;
            }
            if (deposit == ProfessionDepositResult::NoGuild)
            {
                UpdateProfessionObjective(objective, "waiting", "guild_bank_unavailable", currentSkill);
                return;
            }
            if (deposit == ProfessionDepositResult::BankFull)
            {
                UpdateProfessionObjective(objective, "waiting", "guild_bank_full", currentSkill);
                return;
            }
        }

        bool const routed = SetProfessionTravelTarget(objective, bot, botAI);
        UpdateProfessionObjective(
            objective,
            routed ? "active" : "waiting",
            routed ? (bot->GetZoneId() == objective.selectedZoneId ? "gathering_in_zone" : "traveling_to_zone") :
                "profession_zone_unavailable",
            currentSkill);
    }

    void ProcessProfessionObjectiveRows(QueryResult result)
    {
        if (!result)
            return;

        std::unordered_set<uint32> selectedBots;
        do
        {
            ProfessionObjective const objective = ReadProfessionObjective(result->Fetch());

            if (!selectedBots.insert(objective.botGuid).second)
                continue;
            ProcessProfessionObjective(objective);
        } while (result->NextRow());
    }

    void PollProfessionObjectives()
    {
        if (_professionQueryInFlight)
            return;

        _professionQueryInFlight = true;
        _queryProcessor.AddCallback(CharacterDatabase.AsyncQuery(
            "SELECT o.id, o.plan_id, o.bot_guid, o.profession, o.skill_id, o.stage_order, "
            "o.skill_from, o.skill_to, o.min_character_level, o.selected_zone, "
            "o.selected_zone_id, o.tool_item_id, o.deposit_category, o.guild_bank_tab, "
            "o.deposit_free_slots FROM synthetic_profession_objectives o "
            "JOIN synthetic_profession_plans p ON p.id = o.plan_id "
            "JOIN synthetic_persona_bindings b ON b.character_guid = o.bot_guid "
            "WHERE p.status = 'active' AND o.status IN "
            "('queued', 'active', 'waiting', 'depositing') "
            "AND LOWER(b.persona_name) IN ('lyra', 'celene', 'ray', 'browntown') "
            "ORDER BY o.bot_guid, o.last_observed_skill, o.skill_id, o.stage_order").WithCallback(
            [this](QueryResult result)
            {
                _professionQueryInFlight = false;
                ProcessProfessionObjectiveRows(result);
            }));
    }

    void CaptureBotState(uint32 botGuid)
    {
        Player* bot = ObjectAccessor::FindPlayer(PlayerGuid(botGuid));
        PlayerbotAI* botAI = bot ? sPlayerbotsMgr.GetPlayerbotAI(bot) : nullptr;
        if (!bot || !botAI)
            return;

        Unit* target = bot->GetSelectedUnit();
        uint64 const targetGuid = target ? target->GetGUID().GetRawValue() : 0;
        uint8 const targetHealth = target ? ClampPercent(target->GetHealthPct()) : 0;
        Powers const powerType = bot->getPowerType();
        uint8 const powerPercent = ClampPercent(bot->GetPowerPct(powerType));
        bool const prepareActive =
            botAI->HasStrategy("buff", BOT_STATE_NON_COMBAT) ||
            botAI->HasStrategy("bkings", BOT_STATE_NON_COMBAT);

        CharacterDatabase.Execute(Acore::StringFormat(
            "INSERT INTO synthetic_bot_state "
            "(bot_guid, map_id, zone_id, position_x, position_y, position_z, health_pct, "
            "power_pct, in_combat, is_dead, target_guid, target_health_pct, playerbot_state, "
            "follow_active, stay_active, passive_active, prepare_active) "
            "VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}) "
            "ON DUPLICATE KEY UPDATE captured_at = CURRENT_TIMESTAMP, map_id = VALUES(map_id), "
            "zone_id = VALUES(zone_id), position_x = VALUES(position_x), position_y = VALUES(position_y), "
            "position_z = VALUES(position_z), health_pct = VALUES(health_pct), power_pct = VALUES(power_pct), "
            "in_combat = VALUES(in_combat), is_dead = VALUES(is_dead), target_guid = VALUES(target_guid), "
            "target_health_pct = VALUES(target_health_pct), playerbot_state = VALUES(playerbot_state), "
            "follow_active = VALUES(follow_active), stay_active = VALUES(stay_active), "
            "passive_active = VALUES(passive_active), prepare_active = VALUES(prepare_active)",
            botGuid,
            bot->GetMapId(),
            bot->GetZoneId(),
            bot->GetPositionX(),
            bot->GetPositionY(),
            bot->GetPositionZ(),
            ClampPercent(bot->GetHealthPct()),
            powerPercent,
            bot->IsInCombat() ? 1 : 0,
            bot->isDead() ? 1 : 0,
            targetGuid,
            targetHealth,
            static_cast<uint32>(botAI->GetState()),
            botAI->HasStrategy("follow", BOT_STATE_NON_COMBAT) ? 1 : 0,
            botAI->HasStrategy("stay", BOT_STATE_NON_COMBAT) ? 1 : 0,
            botAI->HasStrategy("passive", BOT_STATE_COMBAT) ? 1 : 0,
            prepareActive ? 1 : 0));

        CaptureInventorySnapshot(bot);
    }

    std::string SerializeItemCounts(std::unordered_map<uint32, uint32> const& counts) const
    {
        std::string result = "[";
        bool first = true;
        for (auto const& [entry, count] : counts)
        {
            if (!first)
                result += ",";
            first = false;
            result += Acore::StringFormat("[{},{}]", entry, count);
        }
        result += "]";
        return result;
    }

    void CaptureInventorySnapshot(Player* bot)
    {
        std::unordered_map<uint32, uint32> bagCounts;
        std::unordered_map<uint32, uint32> equipmentCounts;
        uint16 freeBagSlots = 0;

        for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
            if (Item* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                equipmentCounts[item->GetEntry()] += item->GetCount();

        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        {
            if (Item* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                bagCounts[item->GetEntry()] += item->GetCount();
            else
                ++freeBagSlots;
        }

        for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        {
            Bag* bag = bot->GetBagByPos(bagSlot);
            if (!bag)
                continue;
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
            {
                if (Item* item = bag->GetItemByPos(slot))
                    bagCounts[item->GetEntry()] += item->GetCount();
                else
                    ++freeBagSlots;
            }
        }

        CharacterDatabase.Execute(Acore::StringFormat(
            "INSERT INTO synthetic_bot_inventory "
            "(bot_guid, money_copper, free_bag_slots, bag_items_json, equipped_items_json) "
            "VALUES ({}, {}, {}, '{}', '{}') "
            "ON DUPLICATE KEY UPDATE captured_at = CURRENT_TIMESTAMP, "
            "money_copper = VALUES(money_copper), free_bag_slots = VALUES(free_bag_slots), "
            "bag_items_json = VALUES(bag_items_json), equipped_items_json = VALUES(equipped_items_json)",
            bot->GetGUID().GetCounter(),
            bot->GetMoney(),
            freeBagSlots,
            SerializeItemCounts(bagCounts),
            SerializeItemCounts(equipmentCounts)));
    }

    QueryCallbackProcessor _queryProcessor;
    std::unordered_map<uint32, PendingVerification> _pendingVerifications;
    std::unordered_map<uint32, EconomyProfile> _economyProfiles;
    std::unordered_map<uint32, GroupDutyState> _groupDutyStates;
    std::unordered_map<uint32, ProfessionObjective> _activeProfessionObjectives;
    std::unordered_map<uint32, MaterialKitTarget> _activeMaterialTargets;
    std::unordered_map<uint32, std::chrono::steady_clock::time_point> _lastRandomProtection;
    std::unordered_set<uint32> _provisionedRoutineBots;
    std::unordered_set<uint64> _handledIntentIds;
    std::unordered_set<uint64> _unavailableProfessionZones;
    std::vector<std::unique_ptr<ProfessionTravelDestination>> _professionDestinationStorage;
    std::unordered_map<uint64, ProfessionTravelDestination*> _professionDestinations;
    std::unordered_map<uint64, uint16> _professionDestinationRefreshSkill;
    std::deque<uint64> _handledIntentOrder;
    uint32 _intentPollTimer = 0;
    uint32 _snapshotTimer = 0;
    uint32 _economyTimer = 0;
    uint32 _professionTimer = 0;
    bool _intentQueryInFlight = false;
    bool _snapshotQueryInFlight = false;
    bool _economyQueryInFlight = false;
    bool _professionQueryInFlight = false;
    bool _materialKitQueryInFlight = false;
};

class CadiaPersonaProgressionPlayerScript : public PlayerScript
{
public:
    CadiaPersonaProgressionPlayerScript() : PlayerScript(
        "CadiaPersonaProgressionPlayerScript",
        {
            PLAYERHOOK_ON_LOGIN,
            PLAYERHOOK_ON_LEVEL_CHANGED
        })
    {
    }

    void OnPlayerLogin(Player* player) override
    {
        ApplyPreferredTalents(player);
    }

    void OnPlayerLevelChanged(Player* player, uint8 oldLevel) override
    {
        if (oldLevel < player->GetLevel())
            ApplyPreferredTalents(player);
    }

private:
    void ApplyPreferredTalents(Player* player)
    {
        if (!IsEnabled() || !player || !player->GetSession()->IsBot() || player->GetLevel() < 10 ||
            player->GetFreeTalentPoints() == 0)
            return;

        int specNo = -1;
        if (player->GetName() == "Ray" && player->getClass() == CLASS_ROGUE)
            specNo = 1;
        else if (player->GetName() == "Browntown" && player->getClass() == CLASS_MAGE)
            specNo = 2;

        if (specNo < 0)
            return;

        PlayerbotFactory::InitTalentsBySpecNo(player, specNo, true);
        PlayerbotFactory factory(player, player->GetLevel());
        factory.InitGlyphs(false);
        LOG_INFO(
            "module.cadia-director",
            "Applied controlled persona progression template {} to {} at level {}",
            specNo,
            player->GetName(),
            player->GetLevel());
    }

    bool IsEnabled() const
    {
        return directorConfig.GetConfigValue<bool>(DirectorConfigKey::Enabled);
    }
};
}

void Addmod_cadia_player_directorScripts()
{
    new CadiaPlayerDirectorWorldScript();
    new CadiaPersonaProgressionPlayerScript();
}
