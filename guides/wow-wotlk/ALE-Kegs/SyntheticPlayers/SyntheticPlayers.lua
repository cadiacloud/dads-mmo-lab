-- ============================================================================
-- Dad's MMO Lab: Synthetic Players (ALE Lua Bridge)
-- Expansion: Wrath of the Lich King (3.3.5a) / AzerothCore
-- Description: Moves bounded game events and chat through the local synthetic
--              player daemon's MySQL inbox/outbox queues.
-- ============================================================================

local SYNTHETIC = {
    Enabled = true,
    Debug = false,
    PollIntervalMs = 500,
    MaxBatchOutbox = 10,
    TablePrefix = "acore_characters.",
}

-- Only these canonical Playerbots are backed by the persona model. Other
-- Playerbots keep their native deterministic AI and never enter this queue.
local CONTROLLED_PERSONAS = {
    ["lyra"] = true,
    ["celene"] = true,
    ["ray"] = true,
    ["browntown"] = true,
}

local PORTAL_SPELLS = {
    ["STORMWIND"] = 10059,
    ["IRONFORGE"] = 11416,
    ["DARNASSUS"] = 11419,
    ["EXODAR"] = 32266,
    ["THERAMORE"] = 49360,
    ["ORGRIMMAR"] = 11417,
    ["UNDERCITY"] = 11418,
    ["THUNDER BLUFF"] = 11420,
    ["SILVERMOON"] = 32267,
    ["STONARD"] = 49361,
    ["SHATTRATH"] = { 33691, 35717 },
    ["DALARAN"] = 53142,
}

-- Gameobject templates created by the corresponding mage portal spells. The
-- bridge does not treat CastSpell() returning as proof that the normal,
-- reagent-consuming cast completed; it verifies that the expected portal
-- appeared in the world before recording success.
local PORTAL_GAMEOBJECTS_BY_SPELL = {
    [10059] = 176296, -- Stormwind
    [11416] = 176497, -- Ironforge
    [11419] = 176498, -- Darnassus
    [32266] = 182351, -- Exodar
    [49360] = 189993, -- Theramore
    [11417] = 176499, -- Orgrimmar
    [11418] = 176501, -- Undercity
    [11420] = 176500, -- Thunder Bluff
    [32267] = 182352, -- Silvermoon
    [49361] = 189994, -- Stonard
    [33691] = 183384, -- Shattrath (Alliance)
    [35717] = 184594, -- Shattrath (Horde)
    [53142] = 191164, -- Dalaran
}

-- Highest rank first. Ritual of Refreshment creates a clickable table that
-- supplies max-level food and water to party members without a fake trade.
local REFRESHMENT_TABLES_BY_SPELL = {
    [58659] = 193061, -- Ritual of Refreshment, rank 2
    [43987] = 186812, -- Ritual of Refreshment, rank 1
}
local REFRESHMENT_SPELL_PRIORITY = { 58659, 43987 }

-- Highest WotLK Arcane Brilliance rank first. Dalaran Brilliance is accepted
-- as an already-present equivalent but is not required for this character.
local ARCANE_BRILLIANCE_SPELL_PRIORITY = { 43002, 27127, 23028 }
local ARCANE_BRILLIANCE_EQUIVALENTS = { 43002, 27127, 23028, 61316 }

local PENDING_CAST_VERIFICATIONS = {}
local CAST_VERIFY_AFTER_SECONDS = 3
local CAST_VERIFY_TIMEOUT_SECONDS = 18

print(">> [SyntheticPlayers] Loading Synthetic Players ALE bridge...")

local function EscapeSql(value)
    if value == nil then return "" end

    local escaped = tostring(value)
    escaped = string.gsub(escaped, "\\", "\\\\")
    escaped = string.gsub(escaped, "%z", "\\0")
    escaped = string.gsub(escaped, "'", "\\'")
    escaped = string.gsub(escaped, '"', '\\"')
    escaped = string.gsub(escaped, "\n", "\\n")
    escaped = string.gsub(escaped, "\r", "\\r")
    escaped = string.gsub(escaped, "\26", "\\Z")
    return escaped
end

local function LogDebug(message)
    if SYNTHETIC.Debug then
        print("[SyntheticPlayers DEBUG] " .. tostring(message))
    end
end

local function IsHumanPlayer(player)
    return player and player:IsInWorld() and not player:IsBot()
end

local function IsSyntheticTarget(player)
    return player
        and player:IsInWorld()
        and player:IsBot()
        and CONTROLLED_PERSONAS[string.lower(player:GetName() or "")] == true
end

local function HasCadiaAuthority(player)
    if not player or not player:IsInWorld() then return false end

    local result = CharDBQuery(string.format(
        "SELECT 1 FROM %ssynthetic_command_authorities " ..
        "WHERE character_guid = %d AND authority_role = 'CADIA' AND enabled = 1 LIMIT 1;",
        SYNTHETIC.TablePrefix,
        player:GetGUIDLow()
    ))
    return result ~= nil
end

local function IsAcceptedIssuer(player)
    return IsHumanPlayer(player) or HasCadiaAuthority(player)
end

local function IsAuthorizedCommander(botPlayer, issuer)
    if not botPlayer or not issuer then return false end
    local group = botPlayer:GetGroup()
    if not group or not group:IsMember(issuer:GetGUID()) then
        return false
    end

    local issuerGuid = issuer:GetGUID()
    return group:IsLeader(issuerGuid) or group:IsAssistant(issuerGuid) or HasCadiaAuthority(issuer)
end

local function FindFirstBot(players)
    for _, member in ipairs(players or {}) do
        if IsSyntheticTarget(member) then
            return member
        end
    end
    return nil
end

local function FindGroupBot(player)
    local group = player and player:GetGroup() or nil
    return group and FindFirstBot(group:GetMembers()) or nil
end

local function FindMentionedBot(message)
    local explicitName = message and string.match(message, "@([%a][%w]*)") or nil
    if explicitName then
        local explicitPlayer = GetPlayerByName(explicitName)
        if IsSyntheticTarget(explicitPlayer) then return explicitPlayer end
    end

    local normalized = string.lower(message or "")
    for personaName, _ in pairs(CONTROLLED_PERSONAS) do
        if string.match(normalized, "^%s*" .. personaName .. "[%s,:]") then
            local addressedPlayer = GetPlayerByName(personaName)
            if IsSyntheticTarget(addressedPlayer) then return addressedPlayer end
        end
    end
    return nil
end

local function QueueInboxEvent(eventType, sender, target, rawMessage)
    if not IsAcceptedIssuer(sender) then return end

    local senderGuid = sender:GetGUIDLow()
    local senderName = EscapeSql(sender:GetName())
    local senderClass = sender:GetClass()
    local senderRace = sender:GetRace()
    local senderLevel = sender:GetLevel()
    local zoneId = sender:GetZoneId()
    local zoneName = tostring(zoneId)
    local foundArea, areaName = pcall(GetAreaName, zoneId)
    if foundArea and areaName then
        zoneName = areaName
    end

    local targetGuid = 0
    local targetName = ""
    local targetClass = 0
    local targetRace = 0
    local targetLevel = 0

    if IsSyntheticTarget(target) then
        targetGuid = target:GetGUIDLow()
        targetName = EscapeSql(target:GetName())
        targetClass = target:GetClass()
        targetRace = target:GetRace()
        targetLevel = target:GetLevel()
    end

    local sql = string.format(
        "INSERT INTO %ssynthetic_inbox " ..
        "(event_type, sender_guid, sender_name, sender_class, sender_race, sender_level, " ..
        "target_guid, target_name, target_class, target_race, target_level, zone_id, zone_name, raw_message, status) " ..
        "VALUES ('%s', %d, '%s', %d, %d, %d, %d, '%s', %d, %d, %d, %d, '%s', '%s', 0);",
        SYNTHETIC.TablePrefix,
        EscapeSql(eventType),
        senderGuid, senderName, senderClass, senderRace, senderLevel,
        targetGuid, targetName, targetClass, targetRace, targetLevel,
        zoneId, EscapeSql(zoneName), EscapeSql(rawMessage)
    )

    CharDBExecute(sql)
    LogDebug(string.format("Queued %s from %s to %s", eventType, senderName, targetName))
end

local function IsCommand(message)
    local first = message and string.sub(message, 1, 1) or ""
    return first == "." or first == "!" or first == "#"
end

-- Say/yell are routed here. Only explicit @BotName mentions invoke the LLM.
local function OnPlayerChat(event, player, message, chatType, language)
    if not SYNTHETIC.Enabled or not IsAcceptedIssuer(player) or not message or message == "" or IsCommand(message) then
        return
    end

    local target = FindMentionedBot(message)
    if target then
        QueueInboxEvent("CHAT_SAY", player, target, message)
    end
end

local function OnPlayerWhisper(event, player, message, chatType, language, receiver)
    if not SYNTHETIC.Enabled or not IsAcceptedIssuer(player) or not IsSyntheticTarget(receiver) then return end
    if not message or message == "" or IsCommand(message) then return end

    QueueInboxEvent("CHAT_WHISPER", player, receiver, message)
end

local function OnPlayerGroupChat(event, player, message, chatType, language, group)
    if not SYNTHETIC.Enabled or not IsAcceptedIssuer(player) or not message or message == "" or IsCommand(message) then
        return
    end

    local target = FindMentionedBot(message) or (group and FindFirstBot(group:GetMembers()) or nil)
    if target then
        QueueInboxEvent("CHAT_PARTY", player, target, message)
    end
end

local function OnPlayerGuildChat(event, player, message, chatType, language, guild)
    if not SYNTHETIC.Enabled or not IsAcceptedIssuer(player) or not message or message == "" or IsCommand(message) then
        return
    end

    local target = FindMentionedBot(message) or (guild and FindFirstBot(guild:GetMembers()) or nil)
    if target then
        QueueInboxEvent("CHAT_GUILD", player, target, message)
    end
end

local function OnPlayerTextEmote(event, player, textEmote, emoteNum, targetGuid)
    if not SYNTHETIC.Enabled or not IsAcceptedIssuer(player) then return end

    local target = targetGuid and GetPlayerByGUID(targetGuid) or nil
    if IsSyntheticTarget(target) then
        QueueInboxEvent("EVENT_EMOTE", player, target, tostring(textEmote))
    end
end

local function OnPlayerKillCreature(event, player, victim)
    if not SYNTHETIC.Enabled or not IsHumanPlayer(player) or not victim then return end

    local target = FindGroupBot(player)
    if target and (victim:GetRank() >= 1 or victim:IsWorldBoss()) then
        QueueInboxEvent("EVENT_KILL_BOSS", player, target, "Defeated elite/boss: " .. victim:GetName())
    end
end

local function OnPlayerKilledByCreature(event, killer, killed)
    if not SYNTHETIC.Enabled or not IsHumanPlayer(killed) then return end

    local target = FindGroupBot(killed)
    if target then
        QueueInboxEvent("EVENT_DEATH", killed, target, "Died to: " .. (killer and killer:GetName() or "Unknown"))
    end
end

local function OnPlayerLevelChange(event, player, oldLevel)
    if not SYNTHETIC.Enabled or not IsHumanPlayer(player) then return end

    local target = FindGroupBot(player)
    if target then
        QueueInboxEvent(
            "EVENT_LEVEL_UP",
            player,
            target,
            string.format("Level up from %d to %d", oldLevel, player:GetLevel())
        )
    end
end

local function OnPlayerAchievement(event, player, achievement)
    if not SYNTHETIC.Enabled or not IsHumanPlayer(player) or not achievement then return end

    local target = FindGroupBot(player)
    if target then
        QueueInboxEvent(
            "EVENT_ACHIEVEMENT",
            player,
            target,
            string.format("Earned achievement %s (ID: %d)", achievement:GetName(), achievement:GetId())
        )
    end
end

local function DeliverBotMessage(botPlayer, targetPlayer, channelType, message)
    if channelType == "WHISPER" and targetPlayer then
        botPlayer:Whisper(message, 0, targetPlayer)
    elseif channelType == "PARTY" then
        local group = botPlayer:GetGroup()
        if group then
            -- Stock 3.3.5a clients discard a server-forged player party packet
            -- from a bot session even when its wire shape matches native chat.
            -- Use the server-supported system channel as a reliable shared
            -- fallback and label it as party speech. Every human receives the
            -- exact same message and bot-only sessions are skipped.
            local sharedMessage = string.format(
                "|cff66ccff[Party] %s:|r %s",
                botPlayer:GetName(),
                message
            )
            local recipients = 0
            for _, member in ipairs(group:GetMembers() or {}) do
                if IsHumanPlayer(member) then
                    member:SendBroadcastMessage(sharedMessage)
                    recipients = recipients + 1
                end
            end
            print(string.format(
                ">> [SyntheticPlayers] Shared %s party reply with %d human group members.",
                botPlayer:GetName(),
                recipients
            ))
        elseif targetPlayer then
            botPlayer:SendChatMessageToPlayer(2, 0, message, targetPlayer)
        end
    elseif channelType == "GUILD" and targetPlayer then
        botPlayer:SendChatMessageToPlayer(4, 0, message, targetPlayer)
    elseif channelType == "YELL" then
        botPlayer:Yell(message, 0)
    else
        botPlayer:Say(message, 0)
    end
end

local function PlayersShareGroup(firstPlayer, secondPlayer)
    local group = firstPlayer and firstPlayer:GetGroup() or nil
    if not group or not secondPlayer then return false end

    for _, member in ipairs(group:GetMembers() or {}) do
        if member and member:GetGUIDLow() == secondPlayer:GetGUIDLow() then
            return true
        end
    end
    return false
end

local function ResolveKnownPortalSpell(botPlayer, destination)
    local configured = PORTAL_SPELLS[destination]
    if type(configured) == "number" then
        return botPlayer:HasSpell(configured) and configured or nil
    end

    for _, spellId in ipairs(configured or {}) do
        if botPlayer:HasSpell(spellId) then return spellId end
    end
    return nil
end

local function ResolveFirstKnownSpell(botPlayer, spellPriority)
    for _, spellId in ipairs(spellPriority or {}) do
        if botPlayer:HasSpell(spellId) then return spellId end
    end
    return nil
end

local function HasAnyAura(player, spellIds)
    if not player then return false end
    for _, spellId in ipairs(spellIds or {}) do
        if player:HasAura(spellId) then return true end
    end
    return false
end

local function IsPortalNearby(player, gameObjectEntry)
    return player
        and player:IsInWorld()
        and player:GetNearestGameObject(60, gameObjectEntry) ~= nil
end

local function ApplyBoundedAction(botPlayer, targetPlayer, actionCommand)
    if not actionCommand or actionCommand == "" then return true, nil, "no_action" end

    local commandType, commandArgument = string.match(actionCommand, "^(%a+)%s*(.*)$")
    commandType = string.upper(commandType or "")

    if commandType == "EMOTE" then
        local emoteId = tonumber(commandArgument)
        if emoteId and emoteId >= 0 and emoteId <= 500 then
            botPlayer:PerformEmote(emoteId)
            return true, nil, "emote_applied"
        end
    elseif commandType == "STAND" then
        botPlayer:SetStandState(0)
        return true, nil, "posture_applied"
    elseif commandType == "SIT" then
        botPlayer:SetStandState(1)
        return true, nil, "posture_applied"
    elseif commandType == "SLEEP" then
        botPlayer:SetStandState(3)
        return true, nil, "posture_applied"
    elseif commandType == "KNEEL" then
        botPlayer:SetStandState(8)
        return true, nil, "posture_applied"
    elseif commandType == "PORTAL" then
        local destination = string.upper(commandArgument or "")
        if botPlayer:GetClass() ~= 8 then
            return false, "I cannot open mage portals.", "wrong_class"
        end
        if not PlayersShareGroup(botPlayer, targetPlayer) then
            return false, "Join my group first, and then I can open the portal.", "not_grouped"
        end
        if not IsAuthorizedCommander(botPlayer, targetPlayer) then
            return false, "The party leader, raid leader, raid assistant, or Cadia needs to give that order.", "authority_denied"
        end
        if botPlayer:IsInCombat() then
            return false, "I cannot hold a portal open while we are fighting.", "in_combat"
        end

        local spellId = ResolveKnownPortalSpell(botPlayer, destination)
        if not spellId then
            return false, "I do not know the portal to " .. destination .. " yet.", "spell_not_known"
        end


        local gameObjectEntry = PORTAL_GAMEOBJECTS_BY_SPELL[spellId]
        if not gameObjectEntry then
            return false, "That portal route is not safely configured yet.", "portal_mapping_missing"
        end
        if IsPortalNearby(botPlayer, gameObjectEntry) then
            return true, nil, "portal_already_present_" .. tostring(gameObjectEntry)
        end

        botPlayer:MoveStop()
        botPlayer:SetStandState(0)
        botPlayer:CastSpell(botPlayer, spellId, false)
        return true, nil, string.format("cast_requested_%d_%d", spellId, gameObjectEntry)
    elseif commandType == "REFRESHMENT" then
        if botPlayer:GetClass() ~= 8 then
            return false, "I cannot conjure mage refreshments.", "wrong_class"
        end
        if not PlayersShareGroup(botPlayer, targetPlayer) then
            return false, "Join my group first, and I will set out refreshments for everyone.", "not_grouped"
        end
        if not IsAuthorizedCommander(botPlayer, targetPlayer) then
            return false, "The party leader, raid leader, raid assistant, or Cadia needs to give that order.", "authority_denied"
        end
        if botPlayer:IsInCombat() then
            return false, "I cannot set the refreshment table while we are fighting.", "in_combat"
        end

        local spellId = ResolveFirstKnownSpell(botPlayer, REFRESHMENT_SPELL_PRIORITY)
        if not spellId then
            return false, "I do not know the refreshment ritual yet.", "spell_not_known"
        end

        local gameObjectEntry = REFRESHMENT_TABLES_BY_SPELL[spellId]
        if IsPortalNearby(botPlayer, gameObjectEntry) then
            return true, nil, "refreshment_already_present_" .. tostring(gameObjectEntry)
        end

        botPlayer:MoveStop()
        botPlayer:SetStandState(0)
        botPlayer:CastSpell(botPlayer, spellId, false)
        return true, nil, string.format("cast_requested_refreshment_%d_%d", spellId, gameObjectEntry)
    elseif commandType == "BUFF" and string.upper(commandArgument or "") == "ARCANE BRILLIANCE" then
        if botPlayer:GetClass() ~= 8 then
            return false, "I cannot cast Arcane Brilliance.", "wrong_class"
        end
        if not PlayersShareGroup(botPlayer, targetPlayer) then
            return false, "Join my group first, and I will strengthen the party's intellect.", "not_grouped"
        end
        if not IsAuthorizedCommander(botPlayer, targetPlayer) then
            return false, "The party leader, raid leader, raid assistant, or Cadia needs to give that order.", "authority_denied"
        end
        if botPlayer:IsInCombat() then
            return false, "I cannot prepare the party's brilliance while we are fighting.", "in_combat"
        end

        local spellId = ResolveFirstKnownSpell(botPlayer, ARCANE_BRILLIANCE_SPELL_PRIORITY)
        if not spellId then
            return false, "I do not know Arcane Brilliance yet.", "spell_not_known"
        end
        if HasAnyAura(targetPlayer, ARCANE_BRILLIANCE_EQUIVALENTS) then
            return true, nil, "buff_already_present_" .. tostring(spellId)
        end

        botPlayer:MoveStop()
        botPlayer:SetStandState(0)
        botPlayer:CastSpell(botPlayer, spellId, false)
        return true, nil, "cast_requested_buff_" .. tostring(spellId)
    end

    return false, "I cannot perform that action.", "action_not_supported"
end

local function RecordActionAudit(outboxId, botPlayer, actionCommand, actionSuccess, resultCode)
    if not actionCommand or actionCommand == "" then return end

    local outcome = actionSuccess and "accepted" or "rejected"
    if actionSuccess and string.match(resultCode or "", "^cast_requested_") then
        outcome = "requested"
    elseif actionSuccess and (
        string.match(resultCode or "", "^portal_already_present_")
        or string.match(resultCode or "", "^refreshment_already_present_")
        or string.match(resultCode or "", "^buff_already_present_")
    ) then
        outcome = "verified"
    end
    CharDBExecute(string.format(
        "INSERT INTO %ssynthetic_action_audit " ..
        "(outbox_id, bot_guid, bot_name, requested_action, outcome, result_code) " ..
        "VALUES (%d, %d, '%s', '%s', '%s', '%s');",
        SYNTHETIC.TablePrefix,
        outboxId,
        botPlayer:GetGUIDLow(),
        EscapeSql(botPlayer:GetName()),
        EscapeSql(actionCommand),
        outcome,
        EscapeSql(resultCode or "unknown")
    ))
end


local function UpdateActionAudit(outboxId, outcome, resultCode)
    CharDBExecute(string.format(
        "UPDATE %ssynthetic_action_audit SET outcome = '%s', result_code = '%s' WHERE outbox_id = %d;",
        SYNTHETIC.TablePrefix,
        EscapeSql(outcome),
        EscapeSql(resultCode),
        outboxId
    ))
end

local function QueueCastVerification(outboxId, botName, targetName, channelType, resultCode)
    local spellId, gameObjectEntry = string.match(resultCode or "", "^cast_requested_(%d+)_(%d+)$")
    local verificationType = "portal"
    if not spellId or not gameObjectEntry then
        spellId, gameObjectEntry = string.match(
            resultCode or "",
            "^cast_requested_refreshment_(%d+)_(%d+)$"
        )
        verificationType = "refreshment"
    end
    if not spellId then
        spellId = string.match(resultCode or "", "^cast_requested_buff_(%d+)$")
        verificationType = "buff"
    end
    if not spellId then return end

    PENDING_CAST_VERIFICATIONS[outboxId] = {
        bot_name = botName,
        target_name = targetName,
        channel_type = channelType,
        verification_type = verificationType,
        spell_id = tonumber(spellId),
        gameobject_entry = gameObjectEntry and tonumber(gameObjectEntry) or nil,
        requested_at = os.time(),
    }
end

local function VerifyPendingCasts(eventId, delay, calls)
    local now = os.time()

    for outboxId, pending in pairs(PENDING_CAST_VERIFICATIONS) do
        local elapsed = now - pending.requested_at
        if elapsed >= CAST_VERIFY_AFTER_SECONDS then
            local botPlayer = GetPlayerByName(pending.bot_name)
            local targetPlayer = pending.target_name ~= "" and GetPlayerByName(pending.target_name) or nil
            local actionVerified = false
            local verifiedCode = ""

            if pending.verification_type == "buff" then
                actionVerified = HasAnyAura(targetPlayer, ARCANE_BRILLIANCE_EQUIVALENTS)
                    or HasAnyAura(botPlayer, ARCANE_BRILLIANCE_EQUIVALENTS)
                verifiedCode = "buff_present_" .. tostring(pending.spell_id)
            else
                actionVerified = IsPortalNearby(botPlayer, pending.gameobject_entry)
                    or IsPortalNearby(targetPlayer, pending.gameobject_entry)
                verifiedCode = pending.verification_type .. "_present_" .. tostring(pending.gameobject_entry)
            end

            if actionVerified then
                UpdateActionAudit(
                    outboxId,
                    "verified",
                    verifiedCode
                )
                PENDING_CAST_VERIFICATIONS[outboxId] = nil
            elseif elapsed >= CAST_VERIFY_TIMEOUT_SECONDS then
                local failureCode = pending.verification_type .. "_not_observed_" .. tostring(pending.spell_id)
                UpdateActionAudit(
                    outboxId,
                    "failed",
                    failureCode
                )
                if IsSyntheticTarget(botPlayer) then
                    local failureMessage = "The portal spell did not complete. Give me a moment, then ask me to try again."
                    if pending.verification_type == "refreshment" then
                        failureMessage = "The refreshment table did not form. Give me a moment, then ask me to try again."
                    elseif pending.verification_type == "buff" then
                        failureMessage = "The brilliance spell did not take. Give me a moment, then ask me to try again."
                    end
                    DeliverBotMessage(
                        botPlayer,
                        targetPlayer,
                        pending.channel_type,
                        failureMessage
                    )
                elseif targetPlayer then
                    targetPlayer:SendBroadcastMessage(
                        "[SyntheticPlayers] The requested mage action did not complete."
                    )
                end
                PENDING_CAST_VERIFICATIONS[outboxId] = nil
            end
        end
    end
end

local function ProcessSyntheticOutbox(eventId, delay, calls)
    if not SYNTHETIC.Enabled then return end

    local query = string.format(
        "SELECT id, bot_name, target_name, channel_type, message, action_command " ..
        "FROM %ssynthetic_outbox WHERE status = 0 ORDER BY id ASC LIMIT %d;",
        SYNTHETIC.TablePrefix,
        SYNTHETIC.MaxBatchOutbox
    )

    local result = CharDBQuery(query)
    if not result then return end

    repeat
        local outboxId = result:GetUInt32(0)
        local botName = result:GetString(1)
        local targetName = result:GetString(2)
        local channelType = string.upper(result:GetString(3) or "WHISPER")
        local message = result:GetString(4)
        local actionCommand = result:GetString(5)
        local botPlayer = GetPlayerByName(botName)
        local targetPlayer = targetName ~= "" and GetPlayerByName(targetName) or nil
        local deliverySuccess = false

        if IsSyntheticTarget(botPlayer) and message and message ~= "" then
            local actionSuccess, actionFailureMessage, actionResultCode = ApplyBoundedAction(botPlayer, targetPlayer, actionCommand)
            RecordActionAudit(outboxId, botPlayer, actionCommand, actionSuccess, actionResultCode)
            if actionSuccess then
                QueueCastVerification(outboxId, botName, targetName, channelType, actionResultCode)
            end
            if not actionSuccess and actionCommand and actionCommand ~= "" then
                message = actionFailureMessage or "I cannot do that right now."
            end
            DeliverBotMessage(botPlayer, targetPlayer, channelType, message)
            deliverySuccess = true
        elseif targetPlayer and message and message ~= "" then
            targetPlayer:SendBroadcastMessage(string.format("[%s]: %s", botName, message))
            deliverySuccess = true
        end

        local newStatus = deliverySuccess and 1 or 2
        CharDBExecute(string.format(
            "UPDATE %ssynthetic_outbox SET status = %d WHERE id = %d;",
            SYNTHETIC.TablePrefix,
            newStatus,
            outboxId
        ))
        LogDebug(string.format("Processed outbox #%d with status %d", outboxId, newStatus))
    until not result:NextRow()
end

RegisterPlayerEvent(18, OnPlayerChat)              -- ON_CHAT (say/yell)
RegisterPlayerEvent(19, OnPlayerWhisper)           -- ON_WHISPER
RegisterPlayerEvent(20, OnPlayerGroupChat)         -- ON_GROUP_CHAT
RegisterPlayerEvent(21, OnPlayerGuildChat)         -- ON_GUILD_CHAT
RegisterPlayerEvent(24, OnPlayerTextEmote)         -- ON_TEXT_EMOTE
RegisterPlayerEvent(7, OnPlayerKillCreature)       -- ON_KILL_CREATURE
RegisterPlayerEvent(8, OnPlayerKilledByCreature)   -- ON_KILLED_BY_CREATURE
RegisterPlayerEvent(13, OnPlayerLevelChange)       -- ON_LEVEL_CHANGE
RegisterPlayerEvent(45, OnPlayerAchievement)       -- ON_ACHIEVEMENT_COMPLETE

CreateLuaEvent(ProcessSyntheticOutbox, SYNTHETIC.PollIntervalMs, 0)
CreateLuaEvent(VerifyPendingCasts, 1000, 0)

print(">> [SyntheticPlayers] Synthetic Players ALE bridge loaded successfully!")
