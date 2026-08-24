-- Confluent Vanguard full-set bonus for AzerothCore WotLK + ALE.
--
-- WotLK socket enchantments are additive. The level-255 set therefore uses
-- client-visible all-stat socket effects while this script supplies the
-- multiplicative GM scaling as a full-set bonus.

local CONFLUENT_SET_ENTRIES = {
    [900001] = true,
    [900002] = true,
    [900003] = true,
    [900004] = true,
    [900005] = true,
    [900006] = true,
    [900007] = true,
    [900008] = true,
    [900009] = true,
    [900010] = true,
    [900011] = true,
}

local REQUIRED_EQUIPMENT = {
    [0] = 900001,  -- head
    [2] = 900002,  -- shoulders
    [4] = 900003,  -- chest
    [5] = 900006,  -- waist
    [6] = 900005,  -- legs
    [7] = 900007,  -- feet
    [8] = 900008,  -- wrists
    [9] = 900004,  -- hands
    [15] = 900010, -- one-handed sword
    [16] = 900011, -- shield
}

local SOCKET_ENCHANTMENT_SLOTS = { 2, 3, 4 }
local LEGACY_STAMINA_SOCKET_ENCHANT = 3757
local UNIQUE_ALL_STATS_GEM_ENCHANT = 3879
-- Enchantment 3832 is the client-known +10 All Stats chest effect. Unlike
-- 3879 (Nightmare Tear), it has no unique-equipped gem constraint, so it is
-- safe to use as the visible effect in every custom socket.
local ALL_STATS_SOCKET_ENCHANT = 3832

-- The original implementation stacked Elune's Blessing for +100% all stats.
-- Because that ordinary group buff conflicts with Blessing of Kings, paladin
-- companions could replace it and clamp the wearer's health to the lower max.
-- These passive talent effects operate per-stat and stack normally with party
-- buffs. Their forced stacks provide exactly +100% to every primary stat:
--   Endless Winter:       4% Strength   x 25
--   Combat Experience:    4% Agility and Intellect x 25
--   Survivalist:         10% Stamina    x 10
--   Student of the Mind: 10% Spirit     x 10
local LEGACY_FULL_SET_AURA = 26393
local FULL_SET_AURAS = {
    { spell = 49657, stacks = 25 },
    { spell = 34476, stacks = 25 },
    { spell = 19259, stacks = 10 },
    { spell = 44399, stacks = 10 },
}
local CHECK_INTERVAL_MS = 500

local function has_full_set(player)
    for slot, expected_entry in pairs(REQUIRED_EQUIPMENT) do
        local item = player:GetEquippedItemBySlot(slot)
        if not item or item:GetEntry() ~= expected_entry then
            return false
        end
    end

    return true
end

local function normalize_socket_effects(player)
    local changed = false

    for slot in pairs(REQUIRED_EQUIPMENT) do
        local item = player:GetEquippedItemBySlot(slot)
        if item and CONFLUENT_SET_ENTRIES[item:GetEntry()] then
            for _, enchant_slot in ipairs(SOCKET_ENCHANTMENT_SLOTS) do
                local enchantment = item:GetEnchantmentId(enchant_slot)
                if enchantment == LEGACY_STAMINA_SOCKET_ENCHANT
                    or enchantment == UNIQUE_ALL_STATS_GEM_ENCHANT then
                    if item:SetEnchantment(ALL_STATS_SOCKET_ENCHANT, enchant_slot) then
                        changed = true
                    end
                end
            end
        end
    end

    local packed_two_hander = player:GetItemByEntry(900009)
    if packed_two_hander then
        for _, enchant_slot in ipairs(SOCKET_ENCHANTMENT_SLOTS) do
            local enchantment = packed_two_hander:GetEnchantmentId(enchant_slot)
            if enchantment == LEGACY_STAMINA_SOCKET_ENCHANT
                or enchantment == UNIQUE_ALL_STATS_GEM_ENCHANT then
                if packed_two_hander:SetEnchantment(ALL_STATS_SOCKET_ENCHANT, enchant_slot) then
                    changed = true
                end
            end
        end
    end

    if changed then
        player:SaveToDB()
    end
end

local function update_full_set_bonus(player)
    if not player then
        return
    end

    local old_max_health = player:GetMaxHealth()
    local old_max_power = player:GetMaxPower()
    local health_ratio = old_max_health > 0 and player:GetHealth() / old_max_health or 1
    local power_ratio = old_max_power > 0 and player:GetPower() / old_max_power or 1
    local changed = false

    local legacy = player:GetAura(LEGACY_FULL_SET_AURA)
    if legacy then
        legacy:Remove()
        changed = true
    end

    if not has_full_set(player) then
        for _, spec in ipairs(FULL_SET_AURAS) do
            local aura = player:GetAura(spec.spell)
            if aura and aura:GetStackAmount() == spec.stacks then
                aura:Remove()
                changed = true
            end
        end
    else
        for _, spec in ipairs(FULL_SET_AURAS) do
            local aura = player:GetAura(spec.spell)
            if not aura then
                aura = player:AddAura(spec.spell, player)
                changed = true
            end

            if not aura then
                print("[ConfluentVanguard] Failed to apply passive " .. spec.spell)
            elseif aura:GetStackAmount() ~= spec.stacks then
                aura:SetStackAmount(spec.stacks)
                changed = true
            end
        end
    end

    -- Stat-aura transitions alter maximum health and mana immediately. Keep
    -- the same percentage instead of leaving current values at the old cap.
    if changed then
        local new_max_health = player:GetMaxHealth()
        local new_max_power = player:GetMaxPower()
        player:SetHealth(math.max(1, math.floor(new_max_health * health_ratio + 0.5)))
        if new_max_power > 0 then
            player:SetPower(math.floor(new_max_power * power_ratio + 0.5))
        end
    end
end

local function periodic_check(_, _, _, player)
    update_full_set_bonus(player)
end

local function start_for_player(player)
    normalize_socket_effects(player)
    update_full_set_bonus(player)
    player:RegisterEvent(periodic_check, CHECK_INTERVAL_MS, 0)
end

RegisterPlayerEvent(3, function(_, player)
    start_for_player(player)
end)

RegisterPlayerEvent(29, function(_, player)
    player:RegisterEvent(periodic_check, 100, 1)
end)

for _, player in pairs(GetPlayersInWorld()) do
    start_for_player(player)
end
