-- phpMyAdmin SQL Dump
-- version 5.2.1deb3
-- https://www.phpmyadmin.net/
--
-- Host: localhost:3306
-- Generation Time: May 02, 2026 at 09:24 AM
-- Server version: 10.11.14-MariaDB-0ubuntu0.24.04.1
-- PHP Version: 8.3.6

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `pocket_mortys`
--

-- --------------------------------------------------------

--
-- Table structure for table `battles`
--

CREATE TABLE `battles` (
  `battle_id` char(36) NOT NULL,
  `player_id` char(36) NOT NULL,
  `opponent_id` char(36) NOT NULL,
  `wild_morty_id` char(36) DEFAULT NULL,
  `player_active_morty` char(36) DEFAULT NULL,
  `opponent_active_morty` char(36) DEFAULT NULL,
  `opponent_morty_id` char(36) DEFAULT NULL,
  `player_hp` int(11) NOT NULL DEFAULT 0,
  `opponent_hp` int(11) DEFAULT 0,
  `state` enum('ACTIVE','COMPLETED','CANCELLED') DEFAULT 'ACTIVE',
  `winner` char(36) DEFAULT NULL,
  `player_streak` int(11) DEFAULT 0,
  `opponent_streak` int(11) DEFAULT 0,
  `move_log` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`move_log`)),
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Table structure for table `completed_trades`
--

CREATE TABLE `completed_trades` (
  `id` int(11) NOT NULL,
  `completed_trade_id` varchar(64) NOT NULL,
  `request_player_id` varchar(64) NOT NULL,
  `offer_player_id` varchar(64) NOT NULL,
  `morty_request_id` varchar(64) NOT NULL,
  `morty_offer_id` varchar(64) NOT NULL,
  `trade_offer_id` varchar(64) DEFAULT NULL,
  `trade_request_id` varchar(64) DEFAULT NULL,
  `is_free_trade` tinyint(1) DEFAULT 1,
  `fulfilled_at` datetime DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `decks`
--

CREATE TABLE `decks` (
  `id` int(11) NOT NULL,
  `player_id` text DEFAULT NULL,
  `deck_id` int(11) DEFAULT NULL,
  `owned_morty_ids` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `deck_config`
--

CREATE TABLE `deck_config` (
  `id` int(11) NOT NULL,
  `config_id` text NOT NULL DEFAULT 'MP',
  `starting_deck_slots` int(11) NOT NULL DEFAULT 3,
  `max_deck_slots` int(11) NOT NULL DEFAULT 9,
  `cost_additional_slot` int(11) NOT NULL DEFAULT 10
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `events`
--

CREATE TABLE `events` (
  `id` int(11) NOT NULL,
  `raid_event_id` text DEFAULT NULL,
  `shard_id` text DEFAULT NULL,
  `current_state` text NOT NULL,
  `world_id` int(11) DEFAULT NULL,
  `spawn_location` text DEFAULT NULL,
  `boss_id` text DEFAULT NULL,
  `asset_id` text DEFAULT NULL,
  `threat_lvl` int(11) DEFAULT NULL,
  `total_damage` bigint(20) DEFAULT NULL,
  `initial_health` bigint(20) DEFAULT NULL,
  `max_health_bars` bigint(20) DEFAULT NULL,
  `event_state_next_timestamp` timestamp NULL DEFAULT NULL,
  `has_ran` tinyint(1) DEFAULT 0,
  `permit_start` text DEFAULT NULL,
  `permit_buy_in` text DEFAULT NULL,
  `ticket_buy_in` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `event_queue`
--

CREATE TABLE `event_queue` (
  `id` bigint(20) UNSIGNED NOT NULL,
  `room_id` varchar(64) NOT NULL,
  `event_name` varchar(64) NOT NULL,
  `player_id` longtext DEFAULT NULL,
  `emote` text DEFAULT NULL,
  `current_raid` longtext DEFAULT NULL,
  `battle_start` longtext DEFAULT NULL,
  `battle_turn_result` longtext DEFAULT NULL,
  `battle_move_timer_started` longtext DEFAULT NULL,
  `bot_id` text DEFAULT NULL,
  `username` text DEFAULT NULL,
  `player_avatar_id` text DEFAULT NULL,
  `wild_morty_id` varchar(40) DEFAULT NULL,
  `morty_id` text DEFAULT NULL,
  `placement` varchar(255) DEFAULT NULL,
  `x` text DEFAULT NULL,
  `y` text DEFAULT NULL,
  `state` text DEFAULT NULL,
  `division` int(11) DEFAULT NULL,
  `zone_id` text DEFAULT NULL,
  `variant` text DEFAULT NULL,
  `shiny_if_potion` text NOT NULL DEFAULT 'false',
  `payload_json` longtext DEFAULT NULL,
  `pickup_id` char(36) DEFAULT NULL,
  `pick_up_contents` longtext DEFAULT NULL,
  `owned_morties` longtext DEFAULT NULL,
  `only_show_to_player_id` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated` timestamp NOT NULL DEFAULT current_timestamp(),
  `pickup_id_collected_by_player_id` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `friend_list`
--

CREATE TABLE `friend_list` (
  `id` int(11) NOT NULL,
  `player_id_a` text DEFAULT NULL,
  `player_id_b` text DEFAULT NULL,
  `pending` text DEFAULT NULL,
  `direction` text DEFAULT NULL,
  `created` text NOT NULL,
  `modified` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `gachas`
--

CREATE TABLE `gachas` (
  `id` int(11) NOT NULL,
  `gacha_id` varchar(64) NOT NULL,
  `cost` int(11) NOT NULL DEFAULT 0,
  `lvl_min` int(11) NOT NULL,
  `lvl_max` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gachas`
--

INSERT INTO `gachas` (`id`, `gacha_id`, `cost`, `lvl_min`, `lvl_max`) VALUES
(1, 'GachaMPProduct1', 5, 32, 34),
(2, 'GachaMPProduct2', 10, 32, 34),
(3, 'GachaMPProduct3', 30, 32, 34);

-- --------------------------------------------------------

--
-- Table structure for table `gacha_contents`
--

CREATE TABLE `gacha_contents` (
  `id` int(11) NOT NULL,
  `gacha_id` varchar(64) NOT NULL,
  `reward` enum('ITEM','MORTY') NOT NULL,
  `quantity` int(11) NOT NULL DEFAULT 1,
  `division_guarantee` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gacha_contents`
--

INSERT INTO `gacha_contents` (`id`, `gacha_id`, `reward`, `quantity`, `division_guarantee`) VALUES
(1, 'GachaMPProduct1', 'ITEM', 1, NULL),
(2, 'GachaMPProduct1', 'MORTY', 1, NULL),
(3, 'GachaMPProduct1', 'MORTY', 2, 2),
(4, 'GachaMPProduct2', 'MORTY', 1, 3),
(5, 'GachaMPProduct2', 'MORTY', 3, 2),
(6, 'GachaMPProduct2', 'ITEM', 4, NULL),
(7, 'GachaMPProduct2', 'MORTY', 3, NULL),
(8, 'GachaMPProduct3', 'MORTY', 4, 2),
(9, 'GachaMPProduct3', 'MORTY', 3, NULL),
(10, 'GachaMPProduct3', 'MORTY', 1, 4),
(11, 'GachaMPProduct3', 'MORTY', 2, 3),
(12, 'GachaMPProduct3', 'ITEM', 10, NULL);

-- --------------------------------------------------------

--
-- Table structure for table `gacha_content_items`
--

CREATE TABLE `gacha_content_items` (
  `id` int(11) NOT NULL,
  `gacha_content_id` int(11) NOT NULL,
  `item_id` varchar(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gacha_content_items`
--

INSERT INTO `gacha_content_items` (`id`, `gacha_content_id`, `item_id`) VALUES
(1, 1, 'ItemMortyChip'),
(2, 1, 'ItemPureSerum'),
(3, 1, 'ItemHalzinger'),
(4, 1, 'ItemPureHalzinger'),
(5, 1, 'ItemFullRecover'),
(6, 1, 'ItemMrMeeseek'),
(7, 1, 'ItemMegaSeedAttack'),
(8, 1, 'ItemMegaSeedDefence'),
(9, 1, 'ItemMegaSeedSpeed'),
(10, 1, 'ItemMegaSeedLevelUp'),
(11, 6, 'ItemMortyChip'),
(12, 6, 'ItemPureSerum'),
(13, 6, 'ItemHalzinger'),
(14, 6, 'ItemPureHalzinger'),
(15, 6, 'ItemFullRecover'),
(16, 6, 'ItemMrMeeseek'),
(17, 6, 'ItemMegaSeedAttack'),
(18, 6, 'ItemMegaSeedDefence'),
(19, 6, 'ItemMegaSeedSpeed'),
(20, 6, 'ItemMegaSeedLevelUp'),
(21, 12, 'ItemMortyChip'),
(22, 12, 'ItemPureSerum'),
(23, 12, 'ItemHalzinger'),
(24, 12, 'ItemPureHalzinger'),
(25, 12, 'ItemFullRecover'),
(26, 12, 'ItemMrMeeseek'),
(27, 12, 'ItemMegaSeedAttack'),
(28, 12, 'ItemMegaSeedDefence'),
(29, 12, 'ItemMegaSeedSpeed'),
(30, 12, 'ItemMegaSeedLevelUp');

-- --------------------------------------------------------

--
-- Table structure for table `gacha_drop_rates`
--

CREATE TABLE `gacha_drop_rates` (
  `id` int(11) NOT NULL,
  `gacha_promo_id` varchar(64) NOT NULL,
  `division` int(11) NOT NULL,
  `chance` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gacha_drop_rates`
--

INSERT INTO `gacha_drop_rates` (`id`, `gacha_promo_id`, `division`, `chance`) VALUES
(1, 'GachaMPPromo20230207_2026', 1, 80),
(2, 'GachaMPPromo20230207_2026', 2, 12),
(3, 'GachaMPPromo20230207_2026', 3, 6),
(4, 'GachaMPPromo20230207_2026', 4, 2);

-- --------------------------------------------------------

--
-- Table structure for table `gacha_promos`
--

CREATE TABLE `gacha_promos` (
  `id` int(11) NOT NULL,
  `gacha_promo_id` varchar(64) NOT NULL,
  `period_start` int(11) NOT NULL,
  `period_end` int(11) NOT NULL,
  `image_url` text DEFAULT NULL,
  `drop_chance` decimal(8,6) NOT NULL DEFAULT 0.000000,
  `gacha_promo_chance` decimal(8,6) NOT NULL DEFAULT 0.000000,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gacha_promos`
--

INSERT INTO `gacha_promos` (`id`, `gacha_promo_id`, `period_start`, `period_end`, `image_url`, `drop_chance`, `gacha_promo_chance`, `created_at`) VALUES
(1, 'GachaMPPromo20230207_2026', 1769438400, 1780042600, 'https://assets.bps-pmnet.com/Media/Promos/GachaBackgrounds/Cust1605801458922.png', 0.060000, 0.060000, '2026-02-05 21:09:03');

-- --------------------------------------------------------

--
-- Table structure for table `gacha_promo_attack_effects`
--

CREATE TABLE `gacha_promo_attack_effects` (
  `id` int(11) NOT NULL,
  `promo_attack_id` int(11) NOT NULL,
  `effect_type` varchar(32) NOT NULL,
  `stat` varchar(32) DEFAULT NULL,
  `power` int(11) DEFAULT NULL,
  `accuracy` decimal(6,4) DEFAULT NULL,
  `to_self` tinyint(1) DEFAULT NULL,
  `continue_on_miss` tinyint(1) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gacha_promo_attack_effects`
--

INSERT INTO `gacha_promo_attack_effects` (`id`, `promo_attack_id`, `effect_type`, `stat`, `power`, `accuracy`, `to_self`, `continue_on_miss`) VALUES
(1, 1, 'Stat', 'Accuracy', 3, 0.9500, 1, NULL),
(2, 2, 'Hit', NULL, 85, 0.9500, NULL, 0),
(3, 2, 'Poison', NULL, NULL, 1.0000, NULL, NULL),
(4, 3, 'Stat', 'Speed', -2, 0.9500, NULL, NULL),
(5, 4, 'Hit', NULL, 90, 0.7500, NULL, 0),
(6, 4, 'Stat', 'Speed', 1, 0.7500, 1, NULL),
(7, 4, 'Stat', 'Attack', 1, 0.7500, 1, NULL),
(8, 5, 'Hit', NULL, 95, 0.9000, NULL, NULL),
(9, 6, 'Stat', 'Defence', 2, 0.9500, 1, NULL),
(10, 7, 'Hit', NULL, 15, 0.9500, NULL, NULL),
(11, 7, 'Hit', NULL, 20, NULL, NULL, NULL),
(12, 7, 'Hit', NULL, 30, 0.8000, NULL, NULL),
(13, 7, 'Hit', NULL, 35, 0.5000, NULL, NULL),
(14, 8, 'Stat', 'Attack', 2, 0.9500, 1, NULL),
(15, 9, 'Stat', 'Accuracy', 2, 0.8000, 1, NULL),
(16, 9, 'Stat', 'Attack', 2, 0.8000, 1, NULL),
(17, 10, 'Hit', NULL, 120, 0.9500, NULL, NULL),
(18, 11, 'Hit', NULL, 100, 0.9500, NULL, NULL),
(19, 12, 'Stat', 'Accuracy', 2, 0.9500, 1, NULL),
(20, 13, 'Stat', 'Defence', 2, NULL, 1, NULL),
(21, 13, 'Paralyse', NULL, NULL, 0.5000, NULL, 0),
(22, 13, 'Paralyse', NULL, NULL, NULL, 1, NULL),
(23, 14, 'Hit', NULL, 90, 0.9500, NULL, NULL),
(24, 15, 'Stat', 'Defence', 3, 0.9500, 1, NULL),
(25, 16, 'Paralyse', NULL, NULL, 0.6000, NULL, 0),
(26, 16, 'Stat', 'Attack', -1, NULL, NULL, NULL),
(27, 17, 'Hit', NULL, 50, 0.9000, NULL, NULL),
(28, 17, 'Hit', NULL, 50, 0.9000, NULL, 0),
(29, 17, 'Stat', 'Defence', -1, 0.9500, NULL, NULL),
(30, 18, 'Hit', NULL, 100, 0.8000, NULL, NULL),
(31, 19, 'Stat', 'Attack', 3, 0.9500, 1, NULL),
(32, 20, 'Stat', 'Defence', 3, 0.9500, 1, NULL);

-- --------------------------------------------------------

--
-- Table structure for table `gacha_promo_mortys`
--

CREATE TABLE `gacha_promo_mortys` (
  `id` int(11) NOT NULL,
  `gacha_promo_id` varchar(64) NOT NULL,
  `morty_id` varchar(64) NOT NULL,
  `variant` varchar(16) NOT NULL DEFAULT 'Normal',
  `lvl_min` int(11) NOT NULL,
  `lvl_max` int(11) NOT NULL,
  `hp_min` int(11) NOT NULL,
  `hp_max` int(11) NOT NULL,
  `atk_min` int(11) NOT NULL,
  `atk_max` int(11) NOT NULL,
  `def_min` int(11) NOT NULL,
  `def_max` int(11) NOT NULL,
  `spd_min` int(11) NOT NULL,
  `spd_max` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gacha_promo_mortys`
--

INSERT INTO `gacha_promo_mortys` (`id`, `gacha_promo_id`, `morty_id`, `variant`, `lvl_min`, `lvl_max`, `hp_min`, `hp_max`, `atk_min`, `atk_max`, `def_min`, `def_max`, `spd_min`, `spd_max`) VALUES
(1, 'GachaMPPromo20230207_2026', 'MortyBirdingMan', 'Normal', 32, 34, 86, 101, 50, 63, 60, 73, 46, 59),
(2, 'GachaMPPromo20230207_2026', 'MortyChick', 'Normal', 32, 34, 103, 119, 60, 73, 66, 80, 69, 83),
(3, 'GachaMPPromo20230207_2026', 'MortyRobotChicken', 'Normal', 32, 34, 103, 119, 50, 63, 66, 80, 76, 90),
(4, 'GachaMPPromo20230207_2026', 'MortyDrone', 'Normal', 32, 34, 106, 122, 69, 83, 69, 83, 69, 83),
(5, 'GachaMPPromo20230207_2026', 'MortyTurkerSoldier', 'Normal', 32, 34, 98, 114, 50, 63, 49, 62, 50, 63);

-- --------------------------------------------------------

--
-- Table structure for table `gacha_promo_morty_attacks`
--

CREATE TABLE `gacha_promo_morty_attacks` (
  `id` int(11) NOT NULL,
  `gacha_promo_id` varchar(64) NOT NULL,
  `morty_id` varchar(64) NOT NULL,
  `position` int(11) NOT NULL,
  `attack_id` varchar(64) NOT NULL,
  `pp` int(11) NOT NULL,
  `pp_stat` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `gacha_promo_morty_attacks`
--

INSERT INTO `gacha_promo_morty_attacks` (`id`, `gacha_promo_id`, `morty_id`, `position`, `attack_id`, `pp`, `pp_stat`) VALUES
(1, 'GachaMPPromo20230207_2026', 'MortyBirdingMan', 0, 'AttackSparkle', 10, 10),
(2, 'GachaMPPromo20230207_2026', 'MortyBirdingMan', 1, 'AttackArtsyFartsy', 5, 5),
(3, 'GachaMPPromo20230207_2026', 'MortyBirdingMan', 2, 'AttackStarGaze', 15, 15),
(4, 'GachaMPPromo20230207_2026', 'MortyBirdingMan', 3, 'AttackUpbeat', 10, 10),
(5, 'GachaMPPromo20230207_2026', 'MortyChick', 0, 'AttackServingUp', 8, 8),
(6, 'GachaMPPromo20230207_2026', 'MortyChick', 1, 'AttackHarden', 15, 15),
(7, 'GachaMPPromo20230207_2026', 'MortyChick', 2, 'AttackWetTongue', 5, 5),
(8, 'GachaMPPromo20230207_2026', 'MortyChick', 3, 'AttackSalivate', 15, 15),
(9, 'GachaMPPromo20230207_2026', 'MortyRobotChicken', 0, 'AttackLaserStare', 8, 8),
(10, 'GachaMPPromo20230207_2026', 'MortyRobotChicken', 1, 'AttackDinnerTime', 5, 5),
(11, 'GachaMPPromo20230207_2026', 'MortyRobotChicken', 2, 'AttackFlutter', 8, 8),
(12, 'GachaMPPromo20230207_2026', 'MortyRobotChicken', 3, 'AttackBlink', 12, 12),
(13, 'GachaMPPromo20230207_2026', 'MortyDrone', 0, 'AttackStaticShock', 5, 5),
(14, 'GachaMPPromo20230207_2026', 'MortyDrone', 1, 'AttackCrush', 8, 8),
(15, 'GachaMPPromo20230207_2026', 'MortyDrone', 2, 'AttackWall', 10, 10),
(16, 'GachaMPPromo20230207_2026', 'MortyDrone', 3, 'AttackGrab', 5, 5),
(17, 'GachaMPPromo20230207_2026', 'MortyTurkerSoldier', 0, 'AttackPerchAndPoop', 10, 10),
(18, 'GachaMPPromo20230207_2026', 'MortyTurkerSoldier', 1, 'AttackGobbleTango', 5, 5),
(19, 'GachaMPPromo20230207_2026', 'MortyTurkerSoldier', 2, 'AttackPray', 10, 10),
(20, 'GachaMPPromo20230207_2026', 'MortyTurkerSoldier', 3, 'AttackDefend', 10, 10);

-- --------------------------------------------------------

--
-- Table structure for table `mortydex`
--

CREATE TABLE `mortydex` (
  `id` int(11) NOT NULL,
  `player_id` text DEFAULT NULL,
  `morty_id` text DEFAULT NULL,
  `caught` tinytext DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `owned_attacks`
--

CREATE TABLE `owned_attacks` (
  `id` int(11) NOT NULL,
  `owned_morty_id` varchar(255) DEFAULT NULL,
  `attack_id` text DEFAULT NULL,
  `position` int(11) DEFAULT NULL,
  `amount` int(11) DEFAULT NULL,
  `pp` int(11) DEFAULT NULL,
  `pp_stat` int(11) DEFAULT NULL,
  `stat` text DEFAULT NULL,
  `type` text DEFAULT NULL,
  `to_self` int(11) DEFAULT NULL,
  `is_accurate` int(11) DEFAULT NULL,
  `accuracy` tinyint(1) DEFAULT NULL,
  `power` bigint(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `owned_avatars`
--

CREATE TABLE `owned_avatars` (
  `id` int(11) NOT NULL,
  `player_id` text DEFAULT NULL,
  `player_avatar_id` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `owned_items`
--

CREATE TABLE `owned_items` (
  `id` int(11) NOT NULL,
  `player_id` text DEFAULT NULL,
  `item_id` text DEFAULT NULL,
  `quantity` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `owned_morties`
--

CREATE TABLE `owned_morties` (
  `id` int(11) NOT NULL,
  `player_id` text DEFAULT NULL,
  `owned_morty_id` text DEFAULT NULL,
  `morty_id` text DEFAULT NULL,
  `level` bigint(100) DEFAULT NULL,
  `xp` bigint(255) DEFAULT NULL,
  `hp` bigint(255) DEFAULT NULL,
  `hp_stat` bigint(255) DEFAULT NULL,
  `attack_stat` bigint(255) DEFAULT NULL,
  `defence_stat` bigint(255) DEFAULT NULL,
  `variant` text DEFAULT NULL,
  `speed_stat` bigint(255) DEFAULT NULL,
  `is_locked` varchar(255) DEFAULT NULL,
  `is_trading_locked` varchar(255) DEFAULT NULL,
  `fight_pit_id` varchar(255) DEFAULT NULL,
  `evolution_points` bigint(255) DEFAULT NULL,
  `xp_lower` bigint(255) DEFAULT NULL,
  `xp_upper` bigint(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `registered_users`
--

CREATE TABLE `registered_users` (
  `id` int(10) UNSIGNED NOT NULL,
  `email` varchar(190) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `recovery_code_hash` varchar(255) DEFAULT NULL,
  `recovery_code_created_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_login` timestamp NULL DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `room_ids`
--

CREATE TABLE `room_ids` (
  `id` int(11) NOT NULL,
  `room_id` text NOT NULL,
  `room_udp_host` text DEFAULT NULL,
  `room_udp_port` text DEFAULT NULL,
  `world_id` text NOT NULL,
  `zone_id` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `trades`
--

CREATE TABLE `trades` (
  `id` int(11) NOT NULL,
  `trade_id` varchar(64) NOT NULL,
  `player_id` varchar(64) NOT NULL,
  `morty_trade_id` varchar(64) NOT NULL,
  `requested_morty_id` varchar(64) DEFAULT NULL,
  `request_variant` varchar(20) DEFAULT 'Normal',
  `is_free_trade` tinyint(1) DEFAULT 1,
  `created_at` datetime DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `trade_offers`
--

CREATE TABLE `trade_offers` (
  `id` int(11) NOT NULL,
  `trade_offer_id` varchar(64) NOT NULL,
  `trade_id` varchar(64) NOT NULL,
  `player_id` varchar(64) NOT NULL,
  `morty_offer_id` varchar(64) NOT NULL,
  `created_at` datetime DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int(11) UNSIGNED NOT NULL,
  `recovery_code_hash` varchar(255) DEFAULT NULL,
  `secret` varchar(255) NOT NULL,
  `room_id` text DEFAULT NULL,
  `world_id` text DEFAULT NULL,
  `session_id` text DEFAULT NULL,
  `player_id` text DEFAULT NULL,
  `username` text DEFAULT NULL,
  `player_avatar_id` text DEFAULT NULL,
  `level` int(11) DEFAULT NULL,
  `xp` int(11) DEFAULT NULL,
  `streak` int(5) DEFAULT NULL,
  `coins` bigint(255) DEFAULT 0,
  `coupons` bigint(255) DEFAULT 0,
  `permits` bigint(255) DEFAULT 0,
  `wins` bigint(255) NOT NULL DEFAULT 0,
  `losses` bigint(255) NOT NULL DEFAULT 0,
  `active_deck_id` int(10) DEFAULT NULL,
  `decks_owned` int(11) DEFAULT NULL,
  `tags` text DEFAULT NULL,
  `xp_lower` bigint(255) DEFAULT NULL,
  `xp_upper` bigint(255) DEFAULT NULL,
  `donation_request` text DEFAULT NULL,
  `state` text DEFAULT NULL,
  `zone_id` text DEFAULT NULL,
  `expiry_trade` text DEFAULT NULL,
  `last_event_id` bigint(20) DEFAULT 0,
  `last_seen` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created` date NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Table structure for table `user_sessions`
--

CREATE TABLE `user_sessions` (
  `id` bigint(20) UNSIGNED NOT NULL,
  `user_id` int(10) UNSIGNED NOT NULL,
  `token_hash` char(64) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `expires_at` timestamp NOT NULL DEFAULT '0000-00-00 00:00:00',
  `ip` varchar(64) DEFAULT NULL,
  `user_agent` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Indexes for table `battles`
--
ALTER TABLE `battles`
  ADD PRIMARY KEY (`battle_id`),
  ADD KEY `idx_player_id` (`player_id`),
  ADD KEY `idx_opponent_id` (`opponent_id`),
  ADD KEY `idx_state` (`state`);

--
-- Indexes for table `completed_trades`
--
ALTER TABLE `completed_trades`
  ADD PRIMARY KEY (`id`),
  ADD KEY `request_player_id` (`request_player_id`),
  ADD KEY `offer_player_id` (`offer_player_id`);

--
-- Indexes for table `decks`
--
ALTER TABLE `decks`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `deck_config`
--
ALTER TABLE `deck_config`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `events`
--
ALTER TABLE `events`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `event_queue`
--
ALTER TABLE `event_queue`
  ADD PRIMARY KEY (`id`),
  ADD KEY `room_id` (`room_id`,`id`),
  ADD KEY `created_at` (`created_at`);

--
-- Indexes for table `friend_list`
--
ALTER TABLE `friend_list`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `gachas`
--
ALTER TABLE `gachas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `gacha_id` (`gacha_id`);

--
-- Indexes for table `gacha_contents`
--
ALTER TABLE `gacha_contents`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_gacha` (`gacha_id`);

--
-- Indexes for table `gacha_content_items`
--
ALTER TABLE `gacha_content_items`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_content` (`gacha_content_id`);

--
-- Indexes for table `gacha_drop_rates`
--
ALTER TABLE `gacha_drop_rates`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `gacha_promos`
--
ALTER TABLE `gacha_promos`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `gacha_promo_id` (`gacha_promo_id`);

--
-- Indexes for table `gacha_promo_attack_effects`
--
ALTER TABLE `gacha_promo_attack_effects`
  ADD PRIMARY KEY (`id`),
  ADD KEY `promo_attack_id` (`promo_attack_id`);

--
-- Indexes for table `gacha_promo_mortys`
--
ALTER TABLE `gacha_promo_mortys`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_promo_morty` (`gacha_promo_id`,`morty_id`,`variant`),
  ADD KEY `idx_promo` (`gacha_promo_id`);

--
-- Indexes for table `gacha_promo_morty_attacks`
--
ALTER TABLE `gacha_promo_morty_attacks`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_promo_morty` (`gacha_promo_id`,`morty_id`);

--
-- Indexes for table `mortydex`
--
ALTER TABLE `mortydex`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `owned_attacks`
--
ALTER TABLE `owned_attacks`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `owned_avatars`
--
ALTER TABLE `owned_avatars`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `owned_items`
--
ALTER TABLE `owned_items`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `owned_morties`
--
ALTER TABLE `owned_morties`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `registered_users`
--
ALTER TABLE `registered_users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_users_email` (`email`);

--
-- Indexes for table `room_ids`
--
ALTER TABLE `room_ids`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `trades`
--
ALTER TABLE `trades`
  ADD PRIMARY KEY (`id`),
  ADD KEY `trade_id` (`trade_id`),
  ADD KEY `player_id` (`player_id`),
  ADD KEY `owned_morty_id` (`morty_trade_id`);

--
-- Indexes for table `trade_offers`
--
ALTER TABLE `trade_offers`
  ADD PRIMARY KEY (`id`),
  ADD KEY `trade_id` (`trade_id`),
  ADD KEY `player_id` (`player_id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `user_sessions`
--
ALTER TABLE `user_sessions`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_token_hash` (`token_hash`),
  ADD KEY `idx_user_id` (`user_id`),
  ADD KEY `idx_expires` (`expires_at`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `completed_trades`
--
ALTER TABLE `completed_trades`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `decks`
--
ALTER TABLE `decks`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `deck_config`
--
ALTER TABLE `deck_config`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `events`
--
ALTER TABLE `events`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `event_queue`
--
ALTER TABLE `event_queue`
  MODIFY `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `friend_list`
--
ALTER TABLE `friend_list`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gachas`
--
ALTER TABLE `gachas`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gacha_contents`
--
ALTER TABLE `gacha_contents`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gacha_content_items`
--
ALTER TABLE `gacha_content_items`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gacha_drop_rates`
--
ALTER TABLE `gacha_drop_rates`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gacha_promos`
--
ALTER TABLE `gacha_promos`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gacha_promo_attack_effects`
--
ALTER TABLE `gacha_promo_attack_effects`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gacha_promo_mortys`
--
ALTER TABLE `gacha_promo_mortys`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `gacha_promo_morty_attacks`
--
ALTER TABLE `gacha_promo_morty_attacks`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `mortydex`
--
ALTER TABLE `mortydex`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `owned_attacks`
--
ALTER TABLE `owned_attacks`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `owned_avatars`
--
ALTER TABLE `owned_avatars`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `owned_items`
--
ALTER TABLE `owned_items`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `owned_morties`
--
ALTER TABLE `owned_morties`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `registered_users`
--
ALTER TABLE `registered_users`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `room_ids`
--
ALTER TABLE `room_ids`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `trades`
--
ALTER TABLE `trades`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `trade_offers`
--
ALTER TABLE `trade_offers`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int(11) UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- AUTO_INCREMENT for table `user_sessions`
--
ALTER TABLE `user_sessions`
  MODIFY `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=1;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `gacha_content_items`
--
ALTER TABLE `gacha_content_items`
  ADD CONSTRAINT `gacha_content_items_ibfk_1` FOREIGN KEY (`gacha_content_id`) REFERENCES `gacha_contents` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `gacha_promo_attack_effects`
--
ALTER TABLE `gacha_promo_attack_effects`
  ADD CONSTRAINT `gacha_promo_attack_effects_ibfk_1` FOREIGN KEY (`promo_attack_id`) REFERENCES `gacha_promo_morty_attacks` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `user_sessions`
--
ALTER TABLE `user_sessions`
  ADD CONSTRAINT `fk_sessions_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
