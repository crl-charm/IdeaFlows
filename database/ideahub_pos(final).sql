-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Aug 10, 2026 at 11:02 PM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `ideahub_pos`
--

-- --------------------------------------------------------

--
-- Table structure for table `admins`
--

CREATE TABLE `admins` (
  `id` int(11) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `username` varchar(50) NOT NULL,
  `created_at` datetime NOT NULL,
  `password` varchar(255) NOT NULL,
  `failed_login_attempts` int(11) DEFAULT NULL,
  `locked_until` datetime DEFAULT NULL,
  `last_login` datetime DEFAULT NULL,
  `password_changed_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `admins`
--

INSERT INTO `admins` (`id`, `full_name`, `username`, `created_at`, `password`, `failed_login_attempts`, `locked_until`, `last_login`, `password_changed_at`) VALUES
(1, 'Admin', 'admin', '2026-04-28 11:41:20', '$2b$12$D6B4Qe54/QcA/TD.gYwzXeTZwjSO8Lq.8Un0ykNjEXNPx3LB//VJu', 0, NULL, '2026-08-10 19:56:28', '2026-08-10 18:53:53');

-- --------------------------------------------------------

--
-- Table structure for table `boardroom_bookings`
--

CREATE TABLE `boardroom_bookings` (
  `id` int(11) NOT NULL,
  `customer_name` varchar(100) NOT NULL,
  `date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `number_of_people` int(11) NOT NULL,
  `purpose` varchar(255) DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `session_id` int(11) DEFAULT NULL,
  `started_at` datetime DEFAULT NULL,
  `expected_end_at` datetime DEFAULT NULL,
  `ended_at` datetime DEFAULT NULL,
  `extended_minutes` int(11) NOT NULL DEFAULT 0,
  `course` varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `boardroom_bookings`
--

INSERT INTO `boardroom_bookings` (`id`, `customer_name`, `date`, `start_time`, `end_time`, `number_of_people`, `purpose`, `status`, `created_at`, `session_id`, `started_at`, `expected_end_at`, `ended_at`, `extended_minutes`, `course`) VALUES
(1, 'CarltestBook', '2026-04-28', '20:00:00', '20:15:00', 5, 'Sutdy', 'completed', '2026-04-28 12:00:01', NULL, '2026-04-28 12:00:44', '2026-04-28 20:15:00', '2026-04-28 12:06:59', 10, NULL),
(2, 'cac', '2026-04-28', '07:00:00', '08:00:00', 12, '', 'cancelled', '2026-04-28 12:08:44', NULL, NULL, '2026-04-28 08:00:00', NULL, 0, NULL),
(3, 'carl22', '2026-04-28', '07:00:00', '10:00:00', 10, 'study', 'completed', '2026-04-28 12:13:20', NULL, '2026-04-28 12:14:14', '2026-04-28 10:00:00', '2026-04-28 12:17:41', 60, 'it'),
(4, 'carlss', '2026-04-28', '09:00:00', '14:00:00', 20, 'sleep', 'cancelled', '2026-04-28 12:14:09', NULL, NULL, '2026-04-28 14:00:00', NULL, 0, 'it'),
(5, 'gg', '2026-05-08', '20:02:00', '20:30:00', 4, 'STUDY', 'completed', '2026-05-08 12:02:23', 9, '2026-05-08 12:02:27', '2026-05-08 20:30:00', '2026-05-08 12:13:11', 0, 'IT'),
(6, 'asdasf', '2026-05-09', '07:00:00', '08:00:00', 2, '', 'cancelled', '2026-05-08 14:56:56', NULL, NULL, '2026-05-09 08:00:00', NULL, 0, 'asf'),
(7, 'sir', '2026-05-18', '07:00:00', '21:00:00', 4, 'study', 'completed', '2026-05-18 04:41:47', 17, '2026-05-18 04:43:40', '2026-05-18 21:00:00', '2026-05-18 05:30:28', 60, 'it'),
(8, 'varl', '2026-05-21', '07:40:00', '08:00:00', 4, 'study', 'cancelled', '2026-05-20 12:19:06', NULL, NULL, '2026-05-21 08:00:00', NULL, 0, 'it'),
(9, 'varl', '2026-05-20', '10:10:00', '17:15:00', 5, 'study', 'completed', '2026-05-20 14:52:43', 23, '2026-05-20 14:53:10', '2026-05-20 17:15:00', '2026-05-21 13:18:13', 75, 'it'),
(10, 'saver', '2026-05-22', '08:06:00', '16:00:00', 5, 'study', 'booked', '2026-05-22 06:48:27', NULL, NULL, '2026-05-22 16:00:00', NULL, 0, 'it'),
(11, 'Jireh', '2026-08-10', '10:00:00', '14:00:00', 4, 'Hangout', 'completed', '2026-08-09 15:48:43', 35, '2026-08-09 16:17:37', '2026-08-10 14:00:00', '2026-08-09 16:30:39', 0, 'Teacher'),
(12, 'Rybelle', '2026-08-11', '07:00:00', '08:00:00', 10, '', 'completed', '2026-08-10 20:01:08', 45, '2026-08-10 20:01:14', '2026-08-11 08:00:00', '2026-08-10 20:01:42', 0, NULL);

-- --------------------------------------------------------

--
-- Table structure for table `customer_sessions`
--

CREATE TABLE `customer_sessions` (
  `id` int(11) NOT NULL,
  `customer_name` varchar(100) NOT NULL,
  `school` varchar(100) DEFAULT NULL,
  `course` varchar(100) DEFAULT NULL,
  `space_type_id` int(11) NOT NULL,
  `time_in` datetime NOT NULL,
  `time_out` datetime DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `number_of_people` int(11) NOT NULL DEFAULT 1,
  `payment_method` varchar(50) DEFAULT 'cash',
  `amount_tendered` decimal(10,2) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `customer_sessions`
--

INSERT INTO `customer_sessions` (`id`, `customer_name`, `school`, `course`, `space_type_id`, `time_in`, `time_out`, `status`, `number_of_people`, `payment_method`, `amount_tendered`) VALUES
(7, 'carlgwapo', 'ui', 'it', 2, '2026-05-06 13:49:05', '2026-05-06 14:16:49', 'completed', 1, 'cash', NULL),
(8, 'carlsssadas', 'Ui', 'IT', 2, '2026-05-07 12:54:44', '2026-05-07 13:10:26', 'completed', 1, 'cash', NULL),
(9, 'gg', 'Boardroom Booking', 'IT', 3, '2026-05-08 12:02:27', '2026-05-08 12:13:11', 'completed', 4, 'cash', NULL),
(10, 'gsss', 'ui', 'it', 3, '2026-05-08 12:02:47', '2026-05-08 12:13:08', 'completed', 1, 'cash', NULL),
(11, 'car', 'ui', 'it', 2, '2026-05-08 14:45:55', '2026-05-08 14:57:23', 'completed', 1, 'cash', NULL),
(12, 'carl', 'ui', 'iy', 2, '2026-05-10 08:26:19', '2026-05-10 09:51:31', 'completed', 1, 'cash', NULL),
(13, 'asdasdas', 'asd', 'ui', 2, '2026-05-10 10:06:04', '2026-05-12 07:10:12', 'completed', 1, 'cash', NULL),
(14, 'sss', 'ss', 's', 1, '2026-05-12 07:29:52', '2026-05-12 08:39:30', 'completed', 1, 'cash', NULL),
(15, 'kurt', 'ui', 'it', 1, '2026-05-12 12:54:28', '2026-05-18 15:28:35', 'completed', 1, 'gcash', NULL),
(16, 'puala', 'ui', 'it', 2, '2026-05-18 04:34:28', '2026-05-18 15:18:56', 'completed', 1, 'cash', NULL),
(17, 'sir', 'Boardroom Booking', 'it', 3, '2026-05-18 04:43:40', '2026-05-18 05:30:28', 'completed', 4, 'cash', NULL),
(18, 'lion', 'ui', 'it', 2, '2026-05-18 15:19:22', '2026-05-18 15:19:48', 'completed', 1, 'cash', NULL),
(19, 'aula', 'ui', 'it', 2, '2026-05-18 15:31:31', '2026-05-18 15:36:08', 'completed', 2, 'gcash', NULL),
(20, 'oliver', 'ui', 'it', 2, '2026-05-18 16:17:20', '2026-05-18 16:17:45', 'completed', 1, 'gcash', NULL),
(21, 'Mobile', 'Ui', 'It', 2, '2026-05-19 14:41:59', '2026-05-26 06:56:06', 'completed', 1, 'cash', NULL),
(22, 'mac', 'ui', 'it', 2, '2026-05-20 12:09:27', '2026-05-20 12:10:29', 'completed', 1, 'gcash', NULL),
(23, 'varl', 'Boardroom Booking', 'it', 3, '2026-05-20 14:53:10', '2026-05-21 13:18:13', 'completed', 5, 'gcash', NULL),
(24, 'kury', 'ui', 'it', 1, '2026-05-22 06:41:45', '2026-05-22 06:43:19', 'completed', 1, 'cash', NULL),
(25, 'kurty', 'ui', 'it', 1, '2026-05-22 07:07:48', '2026-05-26 06:55:49', 'completed', 1, 'gcash', NULL),
(26, 'NewMenu', 'ui', 'it', 2, '2026-05-26 17:36:52', '2026-05-26 17:39:39', 'completed', 1, 'gcash', NULL),
(27, 'varl', 'calaparan', 'it', 2, '2026-05-28 13:31:38', '2026-05-28 13:33:45', 'completed', 1, 'bdo', NULL),
(28, 'Le Anne', 'ui', 'BSAIS', 2, '2026-05-28 14:01:27', '2026-05-28 14:39:17', 'completed', 1, 'bpi', NULL),
(29, 'Rybelle', 'UI', 'IT', 1, '2026-05-28 14:20:43', '2026-05-28 14:40:09', 'completed', 1, 'gcash', NULL),
(30, 'Erich', 'arroyoo', '6', 2, '2026-05-28 14:42:40', '2026-05-28 14:46:38', 'completed', 1, 'cash', NULL),
(31, 'AJ', 'UI', 'IT', 2, '2026-05-28 14:48:38', '2026-06-29 08:23:00', 'completed', 1, 'gcash', NULL),
(32, 'Saver', '', '', 1, '2026-06-02 07:22:38', '2026-06-29 08:23:04', 'completed', 1, 'bdo', NULL),
(33, 'siomai', 'ui', 'it', 1, '2026-07-20 13:30:04', '2026-07-22 12:36:05', 'completed', 1, 'gcash', NULL),
(34, 'charm', 'ui', 'it', 1, '2026-07-22 13:02:28', '2026-08-09 15:34:02', 'completed', 1, 'bpi', NULL),
(35, 'Jireh', 'Boardroom Booking', 'Teacher', 3, '2026-08-09 16:17:37', '2026-08-09 16:30:39', 'completed', 4, 'cash', 500.00),
(36, 'Clardk', 'ui', 'it', 1, '2026-08-10 16:06:55', '2026-08-10 16:17:18', 'completed', 1, 'cash', 500.00),
(37, 'batman', 'ui', 'it', 2, '2026-08-10 16:23:33', '2026-08-10 16:26:08', 'completed', 1, 'cash', 600.00),
(38, 'jason', 'isat', 'hm', 2, '2026-08-10 16:26:26', '2026-08-10 16:26:53', 'completed', 1, 'gcash', NULL),
(39, 'test', 'test', 'it', 2, '2026-08-10 18:03:04', '2026-08-10 18:03:40', 'completed', 1, 'cash', 500.00),
(40, 'edward', 'ui', 'it', 1, '2026-08-10 19:19:35', '2026-08-10 19:23:11', 'completed', 1, 'cash', 500.00),
(41, 'gcash', 'ui', 'it', 2, '2026-08-10 19:20:30', '2026-08-10 19:45:33', 'completed', 1, 'gcash', NULL),
(42, 'BDO', 'ui', 'it', 2, '2026-08-10 19:20:56', '2026-08-10 19:45:36', 'completed', 1, 'bdo', NULL),
(43, 'BPI', 'ui', 'it', 2, '2026-08-10 19:21:51', '2026-08-10 19:45:39', 'completed', 1, 'bpi', NULL),
(44, 'check', 'ui', 'it', 2, '2026-08-10 19:57:48', NULL, 'active', 1, 'cash', NULL),
(45, 'Rybelle', 'Boardroom Booking', 'N/A', 3, '2026-08-10 20:01:14', '2026-08-10 20:01:42', 'completed', 10, 'cash', 100.00);

-- --------------------------------------------------------

--
-- Table structure for table `daily_sales_reports`
--

CREATE TABLE `daily_sales_reports` (
  `id` int(11) NOT NULL,
  `report_date` date NOT NULL,
  `total_revenue` decimal(12,2) NOT NULL,
  `total_expenses` decimal(12,2) NOT NULL,
  `net_balance` decimal(12,2) NOT NULL,
  `total_orders` int(11) NOT NULL,
  `total_sessions` int(11) NOT NULL,
  `generated_by` int(11) NOT NULL,
  `generated_at` datetime DEFAULT NULL,
  `notes` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `daily_sales_reports`
--

INSERT INTO `daily_sales_reports` (`id`, `report_date`, `total_revenue`, `total_expenses`, `net_balance`, `total_orders`, `total_sessions`, `generated_by`, `generated_at`, `notes`) VALUES
(1, '2026-05-08', 1706.76, 330.00, 1376.76, 3, 3, 2, '2026-05-08 12:12:24', 'smoke'),
(8, '2026-05-07', 330.24, 0.00, 330.24, 2, 1, 2, '2026-05-08 12:13:49', 'TRY'),
(9, '2026-05-12', 3397.90, 1030.00, 2367.90, 1, 1, 2, '2026-05-12 07:52:27', 'soft balancing for todayts 5/12/26 AM'),
(10, '2026-05-18', 0.00, 0.00, 0.00, 2, 2, 2, '2026-05-18 04:55:59', 'trying\n'),
(11, '2026-05-19', 0.00, 0.00, 0.00, 0, 0, 2, '2026-05-18 16:16:56', 'gcash na ni\n'),
(12, '2026-05-20', 555.34, 0.00, 555.34, 1, 1, 2, '2026-05-20 12:11:14', 'gcash payment'),
(13, '2026-05-22', 75.26, 230.00, -154.74, 1, 2, 2, '2026-05-22 07:01:14', ''),
(14, '2026-05-26', 4562.59, 150.00, 4412.59, 0, 0, 2, '2026-05-26 07:23:04', 'try'),
(15, '2026-05-28', 553.56, 0.00, 553.56, 3, 3, 2, '2026-05-28 14:42:12', 'try'),
(16, '2026-06-29', 22613.29, 0.00, 22613.29, 0, 0, 2, '2026-06-29 09:09:42', ''),
(17, '2026-08-10', 1621.94, 0.00, 1621.94, 6, 4, 2, '2026-08-09 16:31:03', 'testliwat'),
(32, '2026-08-11', 0.00, 113.52, -113.52, 0, 0, 2, '2026-08-10 19:11:35', 'test');

-- --------------------------------------------------------

--
-- Table structure for table `expenses`
--

CREATE TABLE `expenses` (
  `id` int(11) NOT NULL,
  `category` varchar(50) NOT NULL,
  `description` text NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `expense_date` date NOT NULL,
  `logged_by` int(11) NOT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `expenses`
--

INSERT INTO `expenses` (`id`, `category`, `description`, `amount`, `expense_date`, `logged_by`, `created_at`) VALUES
(4, 'food', 'CHICKEN', 240.00, '2026-05-08', 2, '2026-05-08 15:09:24'),
(5, 'supplies', 'water delivery', 540.00, '2026-05-12', 2, '2026-05-12 08:34:21'),
(6, 'supplies', 'chicken breast', 490.00, '2026-05-12', 2, '2026-05-12 12:23:25'),
(7, 'transport', 'pleti', 50.00, '2026-05-18', 2, '2026-05-18 05:29:13'),
(8, 'supplies', 'water', 19.99, '2026-05-20', 2, '2026-05-20 14:20:09'),
(9, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-21 13:42:25'),
(10, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-21 13:44:39'),
(11, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-21 13:46:04'),
(12, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-21 14:08:14'),
(13, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-21 14:10:10'),
(14, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-21 14:17:56'),
(15, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-21 14:44:43'),
(16, 'supplies', 'water', 230.00, '2026-05-22', 2, '2026-05-22 07:11:23'),
(17, 'transport', 'pleti', 150.00, '2026-05-26', 2, '2026-05-26 07:22:41'),
(18, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-28 13:00:45'),
(19, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-05-28 13:20:16'),
(20, 'supplies', 'test', 10.00, '2026-05-08', 2, '2026-06-02 08:29:59'),
(30, 'utilities', 'Test utility', 12.34, '2026-08-11', 2, '2026-08-10 17:59:38'),
(31, 'utilities', 'Test utility', 12.34, '2026-08-11', 2, '2026-08-10 18:00:19'),
(32, 'utilities', 'Test utility', 12.34, '2026-08-11', 2, '2026-08-10 18:00:32'),
(34, 'utilities', 'Test utility', 12.34, '2026-08-11', 2, '2026-08-10 18:20:14'),
(35, 'utilities', 'Smoke test expense', 12.34, '2026-08-11', 2, '2026-08-10 18:22:36'),
(36, 'utilities', 'Smoke test expense', 12.34, '2026-08-11', 2, '2026-08-10 18:22:59'),
(37, 'utilities', 'Smoke test expense', 12.34, '2026-08-11', 2, '2026-08-10 18:23:27'),
(38, 'utilities', 'Smoke test expense', 12.34, '2026-08-11', 2, '2026-08-10 18:23:48'),
(39, 'utilities', 'Smoke test expense', 12.34, '2026-08-11', 2, '2026-08-10 18:24:09'),
(40, 'utilities', 'Validation expense', 1.23, '2026-08-11', 2, '2026-08-10 18:41:49'),
(41, 'utilities', 'Validation expense', 1.23, '2026-08-11', 2, '2026-08-10 18:54:16'),
(42, 'supplies', 'test liwat', 123.00, '2026-08-11', 2, '2026-08-10 19:12:25'),
(43, 'food', 'ttesttt', 334.00, '2026-08-10', 2, '2026-08-10 19:17:22'),
(44, 'transport', 'testttagain', 1233.00, '2026-08-10', 2, '2026-08-10 19:17:39');

-- --------------------------------------------------------

--
-- Table structure for table `finance_budgets`
--

CREATE TABLE `finance_budgets` (
  `name` varchar(120) NOT NULL,
  `total_budget` decimal(12,2) NOT NULL,
  `allocated` decimal(12,2) NOT NULL,
  `id` int(11) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `finance_budgets`
--

INSERT INTO `finance_budgets` (`name`, `total_budget`, `allocated`, `id`, `created_at`, `updated_at`) VALUES
('Main Budget', 0.00, 0.00, 1, '2026-05-08 14:29:08', '2026-05-08 14:29:08');

-- --------------------------------------------------------

--
-- Table structure for table `finance_transactions`
--

CREATE TABLE `finance_transactions` (
  `budget_id` int(11) NOT NULL,
  `type` varchar(30) NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `id` int(11) NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `finance_transactions`
--

INSERT INTO `finance_transactions` (`budget_id`, `type`, `amount`, `description`, `id`, `created_at`, `updated_at`) VALUES
(1, 'expense', 10.00, 'smoke-test', 1, '2026-05-08 14:29:09', '2026-05-08 14:29:09'),
(1, 'expense', 10.00, 'smoke-test', 2, '2026-05-08 14:29:37', '2026-05-08 14:29:37'),
(1, 'expense', 10.00, 'smoke-test', 3, '2026-05-08 14:30:56', '2026-05-08 14:30:56'),
(1, 'expense', 10.00, 'smoke-test', 4, '2026-05-08 14:42:25', '2026-05-08 14:42:25'),
(1, 'expense', 10.00, 'smoke-test', 5, '2026-05-08 15:02:49', '2026-05-08 15:02:49'),
(1, 'expense', 10.00, 'smoke-test', 6, '2026-05-08 15:06:18', '2026-05-08 15:06:18'),
(1, 'expense', 10.00, 'smoke-test', 7, '2026-05-21 14:18:00', '2026-05-21 14:18:00'),
(1, 'expense', 10.00, 'smoke-test', 8, '2026-05-21 14:44:46', '2026-05-21 14:44:46'),
(1, 'expense', 10.00, 'smoke-test', 9, '2026-05-28 13:01:02', '2026-05-28 13:01:02'),
(1, 'expense', 10.00, 'smoke-test', 10, '2026-05-28 13:20:28', '2026-05-28 13:20:28'),
(1, 'expense', 10.00, 'smoke-test', 11, '2026-06-02 08:30:03', '2026-06-02 08:30:03');

-- --------------------------------------------------------

--
-- Table structure for table `inventory_items`
--

CREATE TABLE `inventory_items` (
  `id` int(11) NOT NULL,
  `menu_item_id` int(11) NOT NULL,
  `stock_qty` decimal(10,2) NOT NULL DEFAULT 0.00,
  `low_stock_threshold` int(11) NOT NULL,
  `unit` varchar(50) NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `inventory_items`
--

INSERT INTO `inventory_items` (`id`, `menu_item_id`, `stock_qty`, `low_stock_threshold`, `unit`, `created_at`, `updated_at`) VALUES
(20, 96, 45.00, 10, 'pcs', '2026-07-20 14:00:53', '2026-08-10 19:19:57'),
(21, 96, 50.00, 10, 'pcs', '2026-07-20 14:01:15', '2026-07-20 14:01:15'),
(22, 83, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(23, 84, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(24, 85, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(25, 140, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(26, 141, 4.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:50:20'),
(27, 88, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(28, 89, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(29, 90, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(30, 91, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(31, 92, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(32, 93, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(33, 94, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(34, 95, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(35, 97, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(36, 98, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(37, 99, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(38, 100, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(39, 101, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(40, 102, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(41, 103, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(42, 108, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(43, 109, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(44, 110, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(45, 113, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(46, 114, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(47, 115, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(48, 116, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(49, 117, 0.00, 10, 'pieces', '2026-07-20 14:13:35', '2026-07-20 14:13:35'),
(50, 118, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(51, 119, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(52, 120, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(53, 121, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(54, 122, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(55, 123, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(56, 124, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(57, 125, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(58, 126, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(59, 127, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(60, 128, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(61, 129, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(62, 130, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(63, 131, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(64, 132, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(65, 139, 0.00, 10, 'pieces', '2026-07-20 14:13:36', '2026-07-20 14:13:36'),
(66, 142, 3.00, 1, 'klg', '2026-07-20 14:43:59', '2026-07-20 14:43:59'),
(67, 141, 4.00, 1, 'trays', '2026-07-20 14:49:45', '2026-07-20 14:49:45'),
(68, 133, 0.00, 10, 'pieces', '2026-07-22 12:44:22', '2026-07-22 12:44:22'),
(70, 131, 0.00, 10, 'pieces', '2026-07-22 13:34:37', '2026-07-22 16:25:30'),
(71, 144, 1.00, 1, 'klg', '2026-07-22 14:29:05', '2026-08-10 18:03:17'),
(72, 145, 3.68, 1, 'packs', '2026-08-09 15:30:05', '2026-08-10 19:19:57'),
(73, 146, 0.00, 1, 'klg', '2026-08-09 16:24:17', '2026-08-10 16:26:37'),
(74, 147, 3.00, 1, 'packs', '2026-08-09 16:26:32', '2026-08-10 19:21:59'),
(75, 148, 2.75, 1, 'klg', '2026-08-10 16:06:06', '2026-08-10 19:21:25'),
(76, 149, 3.84, 1, 'packs', '2026-08-10 16:07:50', '2026-08-10 19:21:59');

-- --------------------------------------------------------

--
-- Table structure for table `inventory_logs`
--

CREATE TABLE `inventory_logs` (
  `id` int(11) NOT NULL,
  `inventory_item_id` int(11) NOT NULL,
  `change_qty` decimal(10,2) NOT NULL,
  `reason` varchar(100) NOT NULL,
  `changed_by` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `inventory_logs`
--

INSERT INTO `inventory_logs` (`id`, `inventory_item_id`, `change_qty`, `reason`, `changed_by`, `created_at`) VALUES
(13, 20, 10.00, 'admin adjusted +10 (40 → 50) - Restock', 2, '2026-07-20 14:40:23'),
(14, 26, 4.00, 'admin adjusted +4 (0 → 4) - Restock', 2, '2026-07-20 14:50:20'),
(17, 70, 6.00, 'admin adjusted +6 (6 → 12) - Damaged', 2, '2026-07-22 16:25:12'),
(18, 70, -12.00, 'admin adjusted -12 (12 → 0) - Damaged', 2, '2026-07-22 16:25:30'),
(19, 72, 0.00, 'admin linked to Siomai Silog: req=4.0 packs (ratio 0.2000)', 2, '2026-08-09 15:32:01'),
(20, 72, 0.00, 'admin linked to Siomai Silog: req=4.0 pieces (ratio 0.0200)', 2, '2026-08-09 15:32:41'),
(21, 72, -0.08, 'Order deduction for Siomai Silog', NULL, '2026-08-09 15:33:08'),
(22, 73, 0.00, 'admin linked to Chicken-Wings Bonanza: req=2.0 pieces (ratio 0.5000)', 2, '2026-08-09 16:24:54'),
(23, 73, -1.00, 'Order deduction for Chicken-Wings Bonanza', NULL, '2026-08-09 16:25:45'),
(24, 71, -1.00, 'Order deduction for Bangus Silog', NULL, '2026-08-09 16:25:45'),
(25, 20, -1.00, 'Order deduction', NULL, '2026-08-09 16:25:45'),
(26, 74, 0.00, 'admin linked to Coke/Royal: req=1.0 pieces (ratio 0.0005)', 2, '2026-08-09 16:27:46'),
(27, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-09 16:28:08'),
(28, 75, 0.00, 'System linked to Pork Chop: req=1.0 pieces (ratio 0.2500)', NULL, '2026-08-10 16:06:30'),
(29, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-10 16:07:04'),
(30, 75, -0.25, 'Order deduction for Pork Chop', NULL, '2026-08-10 16:07:04'),
(31, 76, 0.00, 'System linked to Bottled Water: req=1.0 pieces (ratio 1.0000)', NULL, '2026-08-10 16:08:03'),
(32, 76, 0.00, 'System linked to Bottled Water: req=1.0 pieces (ratio 0.0100)', NULL, '2026-08-10 16:09:36'),
(33, 76, 0.00, 'System linked to Bottled Water: req=1.0 pieces (ratio 1.0000)', NULL, '2026-08-10 16:10:12'),
(34, 76, 0.00, 'System linked to Bottled Water: req=1.0 pieces (ratio 0.0100)', NULL, '2026-08-10 16:10:31'),
(35, 76, -0.02, 'Order deduction for Bottled Water', NULL, '2026-08-10 16:10:47'),
(36, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-10 16:16:52'),
(37, 76, -0.01, 'Order deduction for Bottled Water', NULL, '2026-08-10 16:16:52'),
(38, 73, -1.00, 'Order deduction for Chicken-Wings Bonanza', NULL, '2026-08-10 16:16:52'),
(39, 72, -0.08, 'Order deduction for Siomai Silog', NULL, '2026-08-10 16:16:52'),
(40, 20, -1.00, 'Order deduction', NULL, '2026-08-10 16:16:52'),
(41, 76, -0.01, 'Order deduction for Bottled Water', NULL, '2026-08-10 16:23:51'),
(42, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-10 16:23:51'),
(43, 71, -1.00, 'Order deduction for Bangus Silog', NULL, '2026-08-10 16:23:51'),
(44, 73, -1.00, 'Order deduction for Chicken-Wings Bonanza', NULL, '2026-08-10 16:23:51'),
(45, 75, -0.25, 'Order deduction for Pork Chop', NULL, '2026-08-10 16:23:51'),
(46, 72, -0.08, 'Order deduction for Siomai Silog', NULL, '2026-08-10 16:23:51'),
(47, 20, -1.00, 'Order deduction', NULL, '2026-08-10 16:23:51'),
(48, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-10 16:26:37'),
(49, 73, -1.00, 'Order deduction for Chicken-Wings Bonanza', NULL, '2026-08-10 16:26:37'),
(50, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-10 18:03:17'),
(51, 76, -0.01, 'Order deduction for Bottled Water', NULL, '2026-08-10 18:03:17'),
(52, 71, -1.00, 'Order deduction for Bangus Silog', NULL, '2026-08-10 18:03:17'),
(53, 75, -0.25, 'Order deduction for Pork Chop', NULL, '2026-08-10 18:03:17'),
(54, 20, -1.00, 'Order deduction', NULL, '2026-08-10 18:03:17'),
(55, 76, -0.01, 'Order deduction for Bottled Water', NULL, '2026-08-10 19:19:57'),
(56, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-10 19:19:57'),
(57, 72, -0.08, 'Order deduction for Siomai Silog', NULL, '2026-08-10 19:19:57'),
(58, 75, -0.25, 'Order deduction for Pork Chop', NULL, '2026-08-10 19:19:57'),
(59, 20, -1.00, 'Order deduction', NULL, '2026-08-10 19:19:57'),
(60, 76, -0.07, 'Order deduction for Bottled Water', NULL, '2026-08-10 19:20:39'),
(61, 75, -0.25, 'Order deduction for Pork Chop', NULL, '2026-08-10 19:21:25'),
(62, 74, 0.00, 'Order deduction for Coke/Royal', NULL, '2026-08-10 19:21:59'),
(63, 76, -0.03, 'Order deduction for Bottled Water', NULL, '2026-08-10 19:21:59');

-- --------------------------------------------------------

--
-- Table structure for table `lounge_bookings`
--

CREATE TABLE `lounge_bookings` (
  `id` int(11) NOT NULL,
  `customer_name` varchar(100) NOT NULL,
  `date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `number_of_people` int(11) NOT NULL,
  `purpose` varchar(255) DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `menu_categories`
--

CREATE TABLE `menu_categories` (
  `id` int(11) NOT NULL,
  `name` varchar(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `menu_categories`
--

INSERT INTO `menu_categories` (`id`, `name`) VALUES
(3, 'Beverages'),
(5, 'Dessert'),
(1, 'Main Dish'),
(2, 'Snack');

-- --------------------------------------------------------

--
-- Table structure for table `menu_items`
--

CREATE TABLE `menu_items` (
  `id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `price` decimal(10,2) DEFAULT NULL,
  `category` varchar(50) DEFAULT NULL,
  `status` varchar(20) DEFAULT NULL,
  `image_url` varchar(255) DEFAULT NULL,
  `is_available` tinyint(1) DEFAULT 1,
  `description` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `menu_items`
--

INSERT INTO `menu_items` (`id`, `name`, `price`, `category`, `status`, `image_url`, `is_available`, `description`, `created_at`, `updated_at`) VALUES
(83, 'Bangus Silog', 145.00, 'Main Dish', 'active', '/static/uploads/menu/menu_c6ef4a4842a24ae18bd8bfbbfc0df2c9.jpg', 1, 'Golden fried bangus paired with garlic rice, egg, and fresh sides.', '2026-05-26 15:52:58', '2026-05-26 15:52:58'),
(84, 'Chicken-Wings Bonanza', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_bb9667b5cd2442ffbd0f9abf5c8fb1c7.jpg', 1, 'Feast of succulent chicken wings, expertly chopped into six delectable pieces and fried to crispy perfections', '2026-05-26 16:00:51', '2026-05-26 16:00:51'),
(85, 'Chorizo Madness', 94.99, 'Main Dish', 'active', '/static/uploads/menu/menu_42e60c32c8f34c17bcbaa7e14eb21cba.jpg', 1, 'Juicy and slightly smoky chorizo bursting with robust flavors paired with egg', '2026-05-26 16:06:17', '2026-05-26 16:06:17'),
(86, 'Cornbeef Silog', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_a918ef73f20a4f94b393c688252c2904.jpg', 1, 'Savory corned beef with garlic rice, egg, and cucumber.', '2026-05-26 16:20:08', '2026-05-26 16:20:08'),
(87, 'Golden Crunch Baconsilog', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_c3c4d04daffa41e8be6745dae464c14f.jpg', 1, 'The best of fried bacon and perfectly cooked egg.', '2026-05-26 16:22:29', '2026-05-26 16:23:38'),
(88, 'Hungarian Sunrise', 119.00, 'Main Dish', 'active', '/static/uploads/menu/menu_f9409ed61e7e4a3eaaecde08e4145046.jpg', 1, 'Smoky hangarian sausage with garlic rice, egg, and fresh sides.', '2026-05-26 16:26:07', '2026-05-26 17:27:50'),
(89, 'Longganisa', 115.00, 'Main Dish', 'active', '/static/uploads/menu/menu_58317631cdd34516a02b93f7ebff08e9.jpg', 1, 'Smoky longganisa served with fried rice, banana, and cucumber', '2026-05-26 16:27:22', '2026-05-26 16:27:22'),
(90, 'Lumpia Silog', 80.00, 'Main Dish', 'active', '/static/uploads/menu/menu_ffb1dbac0d3f4043bda6caf68446e43a.jpg', 1, 'Crispy lumpia with garlic rice, egg, and fresh sides.', '2026-05-26 16:29:06', '2026-05-26 16:29:06'),
(91, 'Siomai Silog', 90.00, 'Main Dish', 'active', '/static/uploads/menu/menu_41f91210e90b4bed8f10ac4e5fa1120a.jpg', 1, 'Steamed Siomai served with garlic rice, fresh cucumber slices, and crispy kropek on the side.', '2026-05-26 16:34:35', '2026-05-26 16:34:35'),
(92, 'Sisig Silog', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_940885bbe22b497cb9fb1431c57be41b.jpg', 1, 'Savory sisig served with garlic rice, egg, banana, and fresh cucumber slices for a flavorful Filipino comfort meal.', '2026-05-26 16:36:13', '2026-05-26 16:36:13'),
(93, 'Spam Silog', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_3c2f799b743149b8bfc0459047ad9b87.jpg', 1, 'Pan-fried spam served with garlic rice, egg, and cucumber', '2026-05-26 16:37:13', '2026-05-26 16:37:13'),
(94, 'Tocino Delight', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_d144f47a85144a3ba249c03f654bc374.jpg', 1, 'Sweet tocino paired with garlic rice, banana, and cucumber', '2026-05-26 16:38:24', '2026-05-26 16:38:24'),
(95, 'Bacon and Egg Burger with Fries', 105.00, 'Snack', 'active', '/static/uploads/menu/menu_03d0e8c80d3842e9958d3a87f7b6ea43.jpg', 1, 'Crispy bacon and fluffy egg layered in a soft toasted bun for a savory and satisfying bite.', '2026-05-26 16:43:04', '2026-06-02 07:18:10'),
(96, 'Cheese Sticks', 59.00, 'Snack', 'active', '/static/uploads/menu/menu_c7e7a248a7334643955a67ca51f887bc.jpg', 1, 'Crispy cheese-filled rolls with creamy dip', '2026-05-26 16:45:26', '2026-05-26 16:45:26'),
(97, 'Chicken Burger', 95.00, 'Snack', 'active', '/static/uploads/menu/menu_c811e1b1caff4925bb803b6ff6ba9de5.jpg', 1, 'Crispy chicken burger with cheese and fresh vegetables', '2026-05-26 16:46:21', '2026-05-26 16:46:21'),
(98, 'Fries Frenzy', 69.00, 'Snack', 'active', '/static/uploads/menu/menu_cd58d6ab56a949dc8a5f78ecd51e54f3.jpg', 1, 'Seasoned fries served with creamy dipping sauce.', '2026-05-26 16:47:12', '2026-05-26 16:47:12'),
(99, 'Ham and Cheese Sandwich', 95.00, 'Snack', 'active', '/static/uploads/menu/menu_dcf36558bcba4e7d9c362aa0e146a644.jpg', 1, 'Toasted Sandwich with ham, cheese, and scrambled egg.', '2026-05-26 16:48:22', '2026-05-26 16:48:22'),
(100, 'Nacho Mania', 105.00, 'Snack', 'active', '/static/uploads/menu/menu_2497902d01a7408fb485dc9295a4e5c7.jpg', 1, 'Crispy nachos loaded with flavorful toppings and creamy cheese sauce for the perfect snack combo', '2026-05-26 16:49:16', '2026-05-26 16:49:16'),
(101, 'Pancit Canton with Siomai', 65.00, 'Snack', 'active', '/static/uploads/menu/menu_41ed4ca588884c36a8c55ed8ff187aca.jpg', 1, 'Savory stir-fried noodles topped with garlic bits and siomai.', '2026-05-26 16:51:16', '2026-07-22 12:34:52'),
(102, 'Siomai', 55.00, 'Snack', 'active', '/static/uploads/menu/menu_aa1f6898f4b74cdbb2ff20cfebd7cb98.jpg', 1, 'Steamed pork dumplings topped with savory sauce and served with calamansi for a flavorful bite-sized snack.', '2026-05-26 16:52:24', '2026-05-26 16:52:24'),
(103, 'Bottled Water', 20.00, 'Beverages', 'active', '/static/uploads/menu/menu_f5893254df1046038aba7cd425158f94.png', 1, NULL, '2026-05-26 16:53:34', '2026-05-26 17:24:38'),
(104, 'Hot VarTestLatte_1779815070818962800', 80.00, 'Beverages', 'deleted', NULL, 0, 'variant test', '2026-05-26 17:04:31', '2026-05-26 17:04:31'),
(105, 'Iced VarTestLatte_1779815070818962800', 95.00, 'Beverages', 'deleted', NULL, 0, 'variant test', '2026-05-26 17:04:31', '2026-05-26 17:04:31'),
(106, 'Hot APITestLatte_1779815293384065100', 80.00, 'Beverages', 'deleted', NULL, 0, 'api variant test', '2026-05-26 17:08:13', '2026-05-26 17:08:18'),
(107, 'Iced APITestLatte_1779815293384065100', 95.00, 'Beverages', 'deleted', NULL, 0, 'api variant test', '2026-05-26 17:08:13', '2026-05-26 17:08:18'),
(108, 'Hot Brewed', 40.00, 'Beverages', 'active', '/static/uploads/menu/menu_8f13eeefac1749c6bf0ff059fa74fee9.webp', 1, NULL, '2026-05-26 17:10:34', '2026-05-26 17:10:34'),
(109, 'Cold Brewed', 50.00, 'Beverages', 'active', '/static/uploads/menu/menu_8f13eeefac1749c6bf0ff059fa74fee9.webp', 1, NULL, '2026-05-26 17:10:34', '2026-05-26 17:10:34'),
(110, 'Calamansi Juice', 29.00, 'Beverages', 'active', '/static/uploads/menu/menu_5bde01ceeb3f4c96bd75e2e3fe4429e5.webp', 1, NULL, '2026-05-26 17:11:13', '2026-05-26 17:11:13'),
(111, 'Hot Hazelnut', 60.00, 'Beverages', 'deleted', '/static/uploads/menu/menu_e224998082b74161af4dbcc29b538600.webp', 0, NULL, '2026-05-26 17:12:12', '2026-05-26 17:20:59'),
(112, 'Cold Hazelnut', 75.00, 'Beverages', 'deleted', '/static/uploads/menu/menu_e224998082b74161af4dbcc29b538600.webp', 0, NULL, '2026-05-26 17:12:12', '2026-05-26 17:19:43'),
(113, 'Hot Coffee with Milk', 50.00, 'Beverages', 'active', '/static/uploads/menu/menu_26de51a28ee446a5ae81046fe9c8a18c.webp', 1, NULL, '2026-05-26 17:12:52', '2026-05-26 17:12:52'),
(114, 'Cold Coffee with Milk', 70.00, 'Beverages', 'active', '/static/uploads/menu/menu_26de51a28ee446a5ae81046fe9c8a18c.webp', 1, NULL, '2026-05-26 17:12:52', '2026-05-26 17:12:52'),
(115, 'Cookies and Cream', 70.00, 'Beverages', 'active', '/static/uploads/menu/menu_06db2f2c42e24156a88c51c43230292c.png', 1, NULL, '2026-05-26 17:13:29', '2026-05-26 17:13:30'),
(116, 'Iced Tea', 40.00, 'Beverages', 'active', '/static/uploads/menu/menu_edd5223ecfb74720a63b4a561a0f6c81.jpg', 1, NULL, '2026-05-26 17:18:41', '2026-05-26 17:18:41'),
(117, 'Hot Hazelnut', 60.00, 'Beverages', 'active', '/static/uploads/menu/menu_c212b15c4c2c449bb7e63c5e2a1aac65.jpg', 1, NULL, '2026-05-26 17:20:08', '2026-05-26 17:20:08'),
(118, 'Cold Hazelnut', 75.00, 'Beverages', 'active', '/static/uploads/menu/menu_c212b15c4c2c449bb7e63c5e2a1aac65.jpg', 1, NULL, '2026-05-26 17:20:08', '2026-05-26 17:20:08'),
(119, 'Lemon Cucumber', 70.00, 'Beverages', 'active', '/static/uploads/menu/menu_a998c8dcca06459d9109e11a0402efcf.jpg', 1, NULL, '2026-05-26 17:20:38', '2026-05-26 17:20:38'),
(120, 'Hot Caramel', 60.00, 'Beverages', 'active', '/static/uploads/menu/menu_ecbd60860f5f4d6f964cf0e6d4c28a58.webp', 1, NULL, '2026-05-26 17:21:46', '2026-05-26 17:21:46'),
(121, 'Cold Caramel', 75.00, 'Beverages', 'active', '/static/uploads/menu/menu_ecbd60860f5f4d6f964cf0e6d4c28a58.webp', 1, NULL, '2026-05-26 17:21:46', '2026-05-26 17:21:46'),
(122, 'Hot Vanilla', 60.00, 'Beverages', 'active', '/static/uploads/menu/menu_d0231f1338854c538b18503586308a00.jpg', 1, NULL, '2026-05-26 17:22:25', '2026-05-26 17:22:25'),
(123, 'Cold Vanilla', 75.00, 'Beverages', 'active', '/static/uploads/menu/menu_d0231f1338854c538b18503586308a00.jpg', 1, NULL, '2026-05-26 17:22:25', '2026-05-26 17:22:25'),
(124, 'Coke/Royal', 25.00, 'Beverages', 'active', '/static/uploads/menu/menu_2cdf2dcf12d64a6e9d2f6966d8c855db.png', 1, NULL, '2026-05-26 17:22:48', '2026-05-26 17:22:48'),
(125, 'Hot Choco', 60.00, 'Beverages', 'active', '/static/uploads/menu/menu_8e6d627ec71849d8b8f522b5da5e3b11.jpg', 1, NULL, '2026-05-26 17:23:56', '2026-05-26 17:23:56'),
(126, 'Cold Choco', 75.00, 'Beverages', 'active', '/static/uploads/menu/menu_8e6d627ec71849d8b8f522b5da5e3b11.jpg', 1, NULL, '2026-05-26 17:23:56', '2026-05-26 17:23:56'),
(127, 'Embutido with Garlic Fried Rice', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_2899f9f81b864f84981dad899575ccbc.webp', 1, 'Classic Filipino embutido served with flavorful garlic fried rice, egg.', '2026-05-26 17:26:58', '2026-05-26 17:26:58'),
(128, 'Hungarian', 109.00, 'Main Dish', 'active', '/static/uploads/menu/menu_301f6d66a3d1438684b541c7bf66ec3e.jpg', 1, 'Hungarian Sausage with Garlic fried rice, egg, and vegetables.', '2026-05-26 17:28:45', '2026-05-26 17:28:45'),
(129, 'Nacho Fried Rice with Porkchop', 139.00, 'Main Dish', 'active', '/static/uploads/menu/menu_d19e5600a6db4e0dbb0eff903d776f15.jpg', 1, 'Crispy porkchop served with flavorful nacho fried rice and refreshing iced tea.', '2026-05-26 17:30:05', '2026-05-26 17:30:05'),
(130, 'Pechopack', 129.00, 'Main Dish', 'active', '/static/uploads/menu/menu_ebdacd2f113a471b85ee6a890ae81000.jpg', 1, 'Crispy pork pecho served with garlic rice, coleslaw, and cucumber.', '2026-05-26 17:31:01', '2026-05-26 17:31:01'),
(131, 'Pork Chop', 145.00, 'Main Dish', 'active', '/static/uploads/menu/menu_8d4f8452b71b48f49a7c10fb02eddfa9.jpg', 1, 'Juicy Pork Chop paired with rice and vegetables', '2026-05-26 17:31:52', '2026-05-26 17:31:52'),
(132, 'Sandwich Bundle with Pancit Canton & Kropek', 249.00, 'Main Dish', 'active', '/static/uploads/menu/menu_a2d294cada9341979889051e2f2560a1.jpg', 1, 'Ham and Cheese sandwiches served with savory pancit canton and crispy kropek on the top.', '2026-05-26 17:35:11', '2026-05-26 17:35:11'),
(133, 'chicken test', 0.00, 'ingredient', 'deleted', NULL, 0, NULL, '2026-05-28 13:00:46', '2026-05-28 13:31:05'),
(134, 'Smoke Menu', 1.00, 'Main Dish', 'deleted', NULL, 0, NULL, '2026-05-28 13:00:46', '2026-05-28 13:34:18'),
(135, 'Smoke Menu', 1.00, 'Main Dish', 'deleted', NULL, 0, NULL, '2026-05-28 13:20:16', '2026-05-28 13:34:20'),
(136, 'Erich', 10.00, 'Main Dish', 'deleted', '/static/uploads/menu/menu_b12c6d189bd344e7a35e4560ee2ab6da.jpg', 0, 'bata nga salawayon', '2026-05-28 14:25:07', '2026-05-28 14:26:05'),
(137, 'Smoke Menu', 1.00, 'Main Dish', 'deleted', NULL, 0, NULL, '2026-06-02 08:29:59', '2026-06-02 13:12:38'),
(138, 'Ice cream', 50.00, 'Snack', 'deleted', NULL, 0, 'milk ice cream', '2026-06-02 13:11:35', '2026-06-02 13:12:00'),
(139, 'ice cream', 50.00, 'Dessert', 'active', NULL, 1, 'ice cream', '2026-06-02 13:14:35', '2026-06-02 13:14:35'),
(140, 'Bacon', 0.00, 'ingredient', 'deleted', NULL, 0, NULL, '2026-07-20 13:51:07', '2026-07-22 12:33:31'),
(141, 'Egg', 0.00, 'ingredient', 'deleted', NULL, 0, NULL, '2026-07-20 13:51:07', '2026-07-22 12:33:40'),
(142, 'Bangus', 0.00, 'ingredient', 'deleted', NULL, 0, NULL, '2026-07-20 14:43:59', '2026-07-22 12:33:34'),
(143, 'Wings', 0.00, 'ingredient', 'deleted', NULL, 0, NULL, '2026-07-22 12:58:10', '2026-07-22 16:21:16'),
(144, 'Fish bangus', 0.00, 'ingredient', 'active', NULL, 1, NULL, '2026-07-22 14:29:05', '2026-07-22 14:29:05'),
(145, 'Sioai', 0.00, 'ingredient', 'active', NULL, 1, NULL, '2026-08-09 15:30:05', '2026-08-09 15:30:05'),
(146, 'Chicken wings', 0.00, 'ingredient', 'active', NULL, 1, NULL, '2026-08-09 16:24:17', '2026-08-09 16:24:17'),
(147, 'Coke', 0.00, 'ingredient', 'active', NULL, 1, NULL, '2026-08-09 16:26:32', '2026-08-09 16:26:32'),
(148, 'Pork', 0.00, 'ingredient', 'active', NULL, 1, NULL, '2026-08-10 16:06:06', '2026-08-10 16:06:06'),
(149, 'Bottled Water', 0.00, 'ingredient', 'active', NULL, 1, NULL, '2026-08-10 16:07:50', '2026-08-10 16:07:50');

-- --------------------------------------------------------

--
-- Table structure for table `menu_item_ingredients`
--

CREATE TABLE `menu_item_ingredients` (
  `id` int(11) NOT NULL,
  `menu_item_id` int(11) NOT NULL,
  `ingredient_item_id` int(11) NOT NULL,
  `quantity_required` decimal(10,2) NOT NULL,
  `unit` varchar(50) DEFAULT NULL,
  `conversion_ratio` decimal(10,4) NOT NULL DEFAULT 1.0000
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `menu_item_ingredients`
--

INSERT INTO `menu_item_ingredients` (`id`, `menu_item_id`, `ingredient_item_id`, `quantity_required`, `unit`, `conversion_ratio`) VALUES
(1, 87, 140, 2.00, NULL, 1.0000),
(2, 87, 141, 3.00, NULL, 1.0000),
(3, 86, 140, 2.00, NULL, 1.0000),
(8, 83, 144, 1.00, NULL, 1.0000),
(10, 91, 145, 4.00, 'pieces', 0.0200),
(11, 84, 146, 2.00, 'pieces', 0.5000),
(12, 124, 147, 1.00, 'pieces', 0.0005),
(13, 131, 148, 1.00, 'pieces', 0.2500),
(17, 103, 149, 1.00, 'pieces', 0.0100);

-- --------------------------------------------------------

--
-- Table structure for table `orders`
--

CREATE TABLE `orders` (
  `id` int(11) NOT NULL,
  `customer_session_id` int(11) NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `handled_by` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `orders`
--

INSERT INTO `orders` (`id`, `customer_session_id`, `created_at`, `status`, `handled_by`) VALUES
(5, 7, '2026-05-06 13:49:16', 'done', 2),
(6, 7, '2026-05-06 14:16:43', 'preparing', 2),
(7, 8, '2026-05-07 12:55:15', 'done', 2),
(8, 8, '2026-05-07 12:55:38', 'done', 2),
(9, 9, '2026-05-08 12:12:43', 'done', 2),
(10, 10, '2026-05-08 12:12:51', 'done', 2),
(11, 11, '2026-05-08 14:47:39', 'done', 2),
(12, 13, '2026-05-12 07:09:48', 'done', 2),
(13, 14, '2026-05-12 08:36:12', 'done', 2),
(14, 15, '2026-05-13 13:39:15', 'done', NULL),
(15, 15, '2026-05-13 14:23:25', 'done', 2),
(16, 16, '2026-05-18 04:37:37', 'done', 2),
(17, 17, '2026-05-18 04:44:02', 'done', 2),
(18, 16, '2026-05-18 15:18:41', 'done', 2),
(19, 18, '2026-05-18 15:19:34', 'done', 2),
(20, 19, '2026-05-18 15:31:39', 'done', 2),
(21, 20, '2026-05-18 16:17:32', 'done', 2),
(22, 21, '2026-05-19 14:42:31', 'done', 2),
(23, 21, '2026-05-19 14:56:44', 'done', NULL),
(24, 22, '2026-05-20 12:09:40', 'done', 2),
(25, 23, '2026-05-20 14:54:30', 'done', 2),
(26, 23, '2026-05-20 14:55:30', 'done', 2),
(27, 24, '2026-05-22 06:41:57', 'done', NULL),
(28, 21, '2026-05-22 07:06:08', 'done', 2),
(29, 26, '2026-05-26 17:38:09', 'done', NULL),
(30, 27, '2026-05-28 13:32:59', 'done', 2),
(31, 28, '2026-05-28 14:03:06', 'done', 2),
(32, 29, '2026-05-28 14:39:46', 'done', NULL),
(33, 30, '2026-05-28 14:44:40', 'done', 2),
(34, 31, '2026-05-28 14:48:55', 'done', 2),
(35, 31, '2026-05-29 13:38:58', 'done', 2),
(36, 31, '2026-05-29 13:40:37', 'done', 2),
(37, 31, '2026-06-02 06:54:25', 'done', 2),
(38, 31, '2026-06-02 07:01:08', 'done', NULL),
(39, 31, '2026-06-02 07:09:00', 'done', 2),
(40, 31, '2026-06-02 07:16:24', 'done', NULL),
(41, 31, '2026-06-02 07:21:34', 'done', NULL),
(42, 32, '2026-06-02 07:22:53', 'done', NULL),
(43, 32, '2026-06-02 13:14:43', 'done', 2),
(44, 32, '2026-06-02 13:14:57', 'done', 2),
(45, 33, '2026-07-20 13:30:17', 'done', 2),
(46, 34, '2026-07-22 13:02:49', 'done', 2),
(47, 34, '2026-08-09 15:33:08', 'done', 2),
(48, 35, '2026-08-09 16:25:44', 'done', 2),
(49, 35, '2026-08-09 16:28:08', 'done', 2),
(50, 36, '2026-08-10 16:07:04', 'done', 2),
(51, 36, '2026-08-10 16:10:47', 'done', 2),
(52, 36, '2026-08-10 16:16:52', 'done', 2),
(53, 37, '2026-08-10 16:23:51', 'done', 22),
(54, 38, '2026-08-10 16:26:37', 'done', 22),
(55, 39, '2026-08-10 18:03:17', 'done', 2),
(56, 40, '2026-08-10 19:19:57', 'done', 2),
(57, 41, '2026-08-10 19:20:39', 'done', 2),
(58, 42, '2026-08-10 19:21:25', 'done', 2),
(59, 43, '2026-08-10 19:21:59', 'done', 2);

-- --------------------------------------------------------

--
-- Table structure for table `order_items`
--

CREATE TABLE `order_items` (
  `id` int(11) NOT NULL,
  `order_id` int(11) NOT NULL,
  `menu_item_id` int(11) NOT NULL,
  `quantity` int(11) DEFAULT NULL,
  `price` decimal(10,2) DEFAULT NULL,
  `status` varchar(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `order_items`
--

INSERT INTO `order_items` (`id`, `order_id`, `menu_item_id`, `quantity`, `price`, `status`) VALUES
(62, 29, 131, 1, 145.00, 'done'),
(63, 29, 123, 1, 75.00, 'done'),
(64, 30, 108, 1, 40.00, 'done'),
(65, 30, 92, 1, 109.00, 'done'),
(66, 31, 98, 1, 69.00, 'done'),
(67, 31, 101, 1, 65.00, 'done'),
(68, 31, 121, 1, 75.00, 'done'),
(69, 32, 108, 1, 40.00, 'done'),
(70, 32, 129, 1, 139.00, 'done'),
(71, 33, 121, 1, 75.00, 'done'),
(72, 33, 115, 1, 70.00, 'done'),
(73, 33, 132, 2, 249.00, 'done'),
(74, 33, 97, 1, 95.00, 'done'),
(75, 33, 101, 1, 65.00, 'done'),
(76, 33, 128, 1, 109.00, 'done'),
(77, 33, 129, 1, 139.00, 'done'),
(78, 34, 83, 1, 145.00, 'done'),
(79, 34, 84, 1, 109.00, 'done'),
(80, 34, 85, 1, 94.99, 'done'),
(81, 35, 99, 1, 95.00, 'done'),
(82, 36, 108, 1, 40.00, 'done'),
(83, 37, 124, 1, 25.00, 'done'),
(84, 37, 85, 1, 94.99, 'done'),
(85, 38, 124, 1, 25.00, 'done'),
(86, 39, 103, 1, 20.00, 'done'),
(87, 39, 110, 1, 29.00, 'done'),
(88, 40, 103, 1, 20.00, 'done'),
(89, 41, 109, 1, 50.00, 'done'),
(90, 41, 124, 1, 25.00, 'done'),
(91, 42, 110, 1, 29.00, 'done'),
(92, 42, 103, 1, 20.00, 'done'),
(93, 43, 139, 1, 50.00, 'done'),
(94, 44, 103, 1, 20.00, 'done'),
(95, 45, 102, 2, 55.00, 'done'),
(96, 46, 84, 1, 109.00, 'done'),
(97, 47, 91, 1, 90.00, 'done'),
(98, 48, 84, 1, 109.00, 'done'),
(99, 48, 83, 1, 145.00, 'done'),
(100, 48, 96, 1, 59.00, 'done'),
(101, 49, 124, 2, 25.00, 'done'),
(102, 50, 124, 1, 25.00, 'done'),
(103, 50, 131, 1, 145.00, 'done'),
(105, 52, 124, 1, 25.00, 'done'),
(106, 52, 103, 1, 20.00, 'done'),
(107, 52, 84, 1, 109.00, 'done'),
(108, 52, 91, 1, 90.00, 'done'),
(109, 52, 96, 1, 59.00, 'done'),
(110, 53, 103, 1, 20.00, 'done'),
(111, 53, 124, 1, 25.00, 'done'),
(112, 53, 83, 1, 145.00, 'done'),
(113, 53, 84, 1, 109.00, 'done'),
(114, 53, 131, 1, 145.00, 'done'),
(115, 53, 91, 1, 90.00, 'done'),
(116, 53, 96, 1, 59.00, 'done'),
(117, 54, 124, 2, 25.00, 'done'),
(118, 54, 84, 1, 109.00, 'done'),
(119, 55, 124, 1, 25.00, 'done'),
(120, 55, 103, 1, 20.00, 'done'),
(121, 55, 83, 1, 145.00, 'done'),
(122, 55, 131, 1, 145.00, 'done'),
(123, 55, 96, 1, 59.00, 'done'),
(124, 56, 103, 1, 20.00, 'done'),
(125, 56, 124, 1, 25.00, 'done'),
(126, 56, 91, 1, 90.00, 'done'),
(127, 56, 131, 1, 145.00, 'done'),
(128, 56, 96, 1, 59.00, 'done'),
(129, 57, 103, 7, 20.00, 'done'),
(130, 58, 131, 1, 145.00, 'done'),
(131, 59, 124, 2, 25.00, 'done'),
(132, 59, 103, 3, 20.00, 'done');

-- --------------------------------------------------------

--
-- Table structure for table `payables`
--

CREATE TABLE `payables` (
  `id` int(11) NOT NULL,
  `creditor_name` varchar(100) NOT NULL,
  `items_description` text NOT NULL,
  `amount_owed` decimal(10,2) NOT NULL,
  `due_date` date NOT NULL,
  `incurred_date` date NOT NULL,
  `status` varchar(30) NOT NULL,
  `partial_paid` decimal(10,2) NOT NULL,
  `created_by` int(11) NOT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `payables`
--

INSERT INTO `payables` (`id`, `creditor_name`, `items_description`, `amount_owed`, `due_date`, `incurred_date`, `status`, `partial_paid`, `created_by`, `created_at`) VALUES
(1, 'Calamansi Juice', '2', 330.00, '2026-05-26', '2026-05-19', 'Paid', 0.00, 2, '2026-05-26 06:44:22'),
(2, 'catyjh', '5', 5000.00, '2026-05-28', '2026-05-28', 'Paid', 0.00, 2, '2026-05-28 14:54:36'),
(3, 'water', 'water', 1000.00, '2026-06-06', '2026-05-29', 'Paid', 0.00, 2, '2026-05-29 13:27:18'),
(4, 'Egg Supplier', '4 trays', 340.00, '2026-07-06', '2026-06-29', 'Paid', 340.00, 2, '2026-06-29 08:24:40'),
(16, 'Test Creditor', 'Test items', 55.55, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 17:59:38'),
(17, 'Test Creditor', 'Test items', 55.55, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 18:00:19'),
(18, 'Test Creditor', 'Test items', 55.55, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 18:00:32'),
(20, 'Test Creditor', 'Test items', 55.55, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 18:20:14'),
(21, 'Test Creditor', 'Test service', 55.55, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 18:23:48'),
(22, 'Test Creditor', 'Test service', 55.55, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 18:24:09'),
(23, 'ValCred', 'x', 5.50, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 18:41:49'),
(24, 'ValCred', 'x', 5.50, '2026-08-20', '2026-08-11', 'Unpaid', 0.00, 2, '2026-08-10 18:54:16'),
(26, 'test', 'test', 123.00, '2026-08-11', '2026-08-10', 'Unpaid', 0.00, 2, '2026-08-10 19:13:19'),
(27, 'carl', 'carl', 123.00, '2026-08-13', '2026-08-11', 'Partially Paid', 12.00, 2, '2026-08-10 19:15:04');

-- --------------------------------------------------------

--
-- Table structure for table `receivables`
--

CREATE TABLE `receivables` (
  `id` int(11) NOT NULL,
  `customer_name` varchar(100) NOT NULL,
  `customer_contact` varchar(100) DEFAULT NULL,
  `items_description` text NOT NULL,
  `amount_owed` decimal(10,2) NOT NULL,
  `due_date` date NOT NULL,
  `paid` tinyint(1) NOT NULL,
  `partial_paid` decimal(10,2) NOT NULL,
  `created_by` int(11) NOT NULL,
  `session_id` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `approved_by_staff` varchar(100) DEFAULT NULL,
  `paid_at` datetime DEFAULT NULL,
  `incurred_date` date DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `receivables`
--

INSERT INTO `receivables` (`id`, `customer_name`, `customer_contact`, `items_description`, `amount_owed`, `due_date`, `paid`, `partial_paid`, `created_by`, `session_id`, `created_at`, `approved_by_staff`, `paid_at`, `incurred_date`) VALUES
(1, 'george', '090-900-891243', 'TAKES TUBIG BEEF CALDERITA AND BULALO AND RICE', 650.00, '2026-05-08', 1, 0.00, 2, NULL, '2026-05-08 15:08:45', NULL, NULL, NULL),
(2, 'mix', '097890789240', 'siomai rice', 250.00, '2026-05-12', 1, 0.00, 2, NULL, '2026-05-12 08:35:07', NULL, NULL, NULL),
(3, 'aj', '09087860', 'red horse', 340.00, '2026-05-15', 1, 0.00, 2, NULL, '2026-05-12 12:24:10', NULL, NULL, NULL),
(4, 'june', '099788738', 'test', 134.00, '2026-05-13', 1, 0.00, 2, NULL, '2026-05-13 13:40:02', NULL, NULL, NULL),
(5, 'tessss', '3455', 'asdsa', 3435.00, '2026-05-13', 1, 0.00, 2, NULL, '2026-05-13 13:46:32', NULL, NULL, NULL),
(6, 'joish', '0997478948', 'coffee ', 544.00, '2026-05-14', 1, 0.00, 2, NULL, '2026-05-13 14:17:35', NULL, NULL, NULL),
(7, 'paula', '0980-89009', 'water', 340.00, '2026-05-15', 1, 0.00, 2, NULL, '2026-05-14 07:30:01', NULL, NULL, NULL),
(8, 'paulo', '9090898990-89', 'food', 340.00, '2026-05-14', 1, 0.00, 2, NULL, '2026-05-14 07:40:27', NULL, NULL, NULL),
(9, 'mix', '099485099', 'dinner', 333.00, '2026-05-20', 1, 0.00, 2, NULL, '2026-05-20 14:23:22', NULL, NULL, NULL),
(10, 'wonyx', '0998908589', 'food', 220.00, '2026-05-21', 1, 0.00, 2, NULL, '2026-05-20 14:25:41', NULL, NULL, NULL),
(11, 'jera', '67886778', 'dinner', 239.00, '2026-05-22', 1, 0.00, 2, NULL, '2026-05-22 07:12:38', NULL, NULL, NULL),
(12, 'guard', '889789778', '', 400.00, '2026-05-22', 1, 0.00, 2, NULL, '2026-05-22 07:48:40', NULL, NULL, NULL),
(13, 'paolo', '09089089098', 'calamansi juice', 450.00, '2026-05-27', 1, 0.00, 2, NULL, '2026-05-26 06:45:23', 'Kurt', '2026-05-28 14:41:30', NULL),
(14, 'paolo', '09089089098', 'beef tapa', 120.00, '2026-05-31', 1, 0.00, 2, NULL, '2026-05-26 06:51:24', 'jera', '2026-05-28 14:41:38', NULL),
(19, 'paolo', '09089089098', 'water', 99.95, '2026-06-10', 1, 0.00, 2, NULL, '2026-05-28 14:35:13', 'rybelle', '2026-05-28 14:41:44', '2026-05-28'),
(20, 'Rybelle', '09089089098', 'kjk,nk', 999.96, '2026-06-06', 1, 0.00, 2, NULL, '2026-05-28 14:51:17', 'rybelle', '2026-06-02 07:03:43', '2026-05-28'),
(21, 'Rybelle', '09089089098', 'bangus silog', 100.00, '2026-06-06', 1, 0.00, 2, NULL, '2026-05-29 13:24:43', 'rybelle', '2026-06-02 13:10:26', '2026-05-29'),
(24, 'Rybelle', '09089089098', 'siomai', 229.99, '2026-06-03', 1, 0.00, 2, NULL, '2026-06-02 13:10:20', 'Carl', '2026-06-02 13:10:26', '2026-06-02'),
(31, 'Test Customer', '1234567890', 'Service', 66.66, '2026-08-20', 1, 0.00, 2, NULL, '2026-08-10 17:59:38', 'admin', '2026-08-10 19:18:25', '2026-08-11'),
(32, 'Test Customer', '1234567890', 'Service', 66.66, '2026-08-20', 1, 0.00, 2, NULL, '2026-08-10 18:00:19', 'admin', '2026-08-10 19:18:25', '2026-08-11'),
(33, 'Test Customer', '1234567890', 'Service', 66.66, '2026-08-20', 1, 0.00, 2, NULL, '2026-08-10 18:00:32', 'admin', '2026-08-10 19:18:25', '2026-08-11'),
(35, 'Test Customer', '1234567890', 'Service', 66.66, '2026-08-20', 1, 0.00, 2, NULL, '2026-08-10 18:20:14', 'admin', '2026-08-10 19:18:25', '2026-08-11'),
(36, 'Test Customer', '1234567890', 'Service', 66.66, '2026-08-20', 1, 0.00, 2, NULL, '2026-08-10 18:23:48', NULL, '2026-08-10 19:18:25', '2026-08-11'),
(37, 'Test Customer', '1234567890', 'Service', 66.66, '2026-08-20', 1, 0.00, 2, NULL, '2026-08-10 18:24:09', NULL, '2026-08-10 19:18:25', '2026-08-11'),
(38, 'test liwat', '099387875', 'test', 123.00, '2026-08-12', 0, 0.00, 2, NULL, '2026-08-10 19:13:04', 'Superman', NULL, '2026-08-10');

-- --------------------------------------------------------

--
-- Table structure for table `soft_balance_entries`
--

CREATE TABLE `soft_balance_entries` (
  `id` int(11) NOT NULL,
  `balance_date` date NOT NULL,
  `period` varchar(2) NOT NULL,
  `total_revenue` decimal(12,2) NOT NULL,
  `total_expenses` decimal(12,2) NOT NULL,
  `net_balance` decimal(12,2) NOT NULL,
  `notes` text DEFAULT NULL,
  `generated_by` int(11) NOT NULL,
  `generated_at` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `soft_balance_entries`
--

INSERT INTO `soft_balance_entries` (`id`, `balance_date`, `period`, `total_revenue`, `total_expenses`, `net_balance`, `notes`, `generated_by`, `generated_at`) VALUES
(1, '2026-05-08', 'AM', 1172.94, 0.00, 1172.94, 'smoke', 2, '2026-05-08 14:42:25'),
(2, '2026-05-08', 'AM', 1706.76, 10.00, 1696.76, 'smoke', 2, '2026-05-08 15:02:46'),
(3, '2026-05-08', 'AM', 1706.76, 20.00, 1686.76, 'smoke', 2, '2026-05-08 15:06:16'),
(4, '2026-05-08', 'AM', 1706.76, 240.00, 1466.76, 'NA', 2, '2026-05-08 15:10:24'),
(5, '2026-05-12', 'PM', 1846.29, 0.00, 1846.29, 'TESTING\n', 2, '2026-05-12 07:52:27'),
(6, '2026-05-12', 'PM', 1846.29, 540.00, 1306.29, 'PMPMMM', 2, '2026-05-12 08:37:31'),
(7, '2026-05-12', 'AM', 3397.90, 540.00, 2857.90, 'pmgets', 2, '2026-05-12 08:40:57'),
(8, '2026-05-12', 'AM', 3397.90, 1030.00, 2367.90, 'soft balancing for todayts 5/12/26 AM', 2, '2026-05-12 12:26:04'),
(9, '2026-05-18', 'AM', 0.00, 0.00, 0.00, 'trying\n', 2, '2026-05-18 04:55:59'),
(10, '2026-05-19', 'PM', 0.00, 0.00, 0.00, 'with gcash payment', 2, '2026-05-18 16:16:56'),
(11, '2026-05-19', 'PM', 0.00, 0.00, 0.00, 'gcash na ni\n', 2, '2026-05-18 16:17:59'),
(12, '2026-05-20', 'PM', 555.34, 0.00, 555.34, 'gcash payment', 2, '2026-05-20 12:11:14'),
(13, '2026-05-08', 'AM', 1706.76, 240.00, 1466.76, 'smoke', 2, '2026-05-21 13:42:25'),
(14, '2026-05-08', 'AM', 1706.76, 250.00, 1456.76, 'smoke', 2, '2026-05-21 13:44:39'),
(15, '2026-05-08', 'AM', 1706.76, 260.00, 1446.76, 'smoke', 2, '2026-05-21 13:46:04'),
(16, '2026-05-08', 'AM', 1706.76, 270.00, 1436.76, 'smoke', 2, '2026-05-21 14:08:14'),
(17, '2026-05-08', 'AM', 1706.76, 280.00, 1426.76, 'smoke', 2, '2026-05-21 14:10:10'),
(18, '2026-05-08', 'AM', 1706.76, 290.00, 1416.76, 'smoke', 2, '2026-05-21 14:17:56'),
(19, '2026-05-08', 'AM', 1706.76, 300.00, 1406.76, 'smoke', 2, '2026-05-21 14:44:43'),
(20, '2026-05-22', 'AM', 75.26, 0.00, 75.26, '', 2, '2026-05-22 07:01:14'),
(21, '2026-05-22', 'PM', 75.26, 230.00, -154.74, '', 2, '2026-05-22 07:14:00'),
(22, '2026-05-26', 'PM', 4562.59, 150.00, 4412.59, 'try', 2, '2026-05-26 07:23:04'),
(23, '2026-05-08', 'AM', 1706.76, 310.00, 1396.76, 'smoke', 2, '2026-05-28 13:00:45'),
(24, '2026-05-08', 'AM', 1706.76, 320.00, 1386.76, 'smoke', 2, '2026-05-28 13:20:16'),
(25, '2026-05-28', 'PM', 553.56, 0.00, 553.56, 'try', 2, '2026-05-28 14:42:12'),
(26, '2026-05-08', 'AM', 1706.76, 330.00, 1376.76, 'smoke', 2, '2026-06-02 08:29:59'),
(27, '2026-06-29', 'PM', 22613.29, 0.00, 22613.29, '', 2, '2026-06-29 09:09:42'),
(28, '2026-08-10', 'AM', 0.00, 0.00, 0.00, 'Testagain', 2, '2026-08-09 16:31:03'),
(48, '2026-08-11', 'AM', 0.00, 12.34, -12.34, 'Test soft balance', 2, '2026-08-10 17:59:38'),
(49, '2026-08-11', 'AM', 0.00, 24.68, -24.68, 'Test soft balance', 2, '2026-08-10 18:00:19'),
(50, '2026-08-11', 'AM', 0.00, 37.02, -37.02, 'Test soft balance', 2, '2026-08-10 18:00:32'),
(58, '2026-08-11', 'AM', 0.00, 49.36, -49.36, 'Test soft balance', 2, '2026-08-10 18:20:14'),
(59, '2026-08-11', 'AM', 0.00, 98.72, -98.72, 'Test soft balance', 2, '2026-08-10 18:23:48'),
(60, '2026-08-11', 'AM', 0.00, 111.06, -111.06, 'Test soft balance', 2, '2026-08-10 18:24:09'),
(65, '2026-08-11', 'PM', 0.00, 113.52, -113.52, 'test', 2, '2026-08-10 19:11:35'),
(66, '2026-08-10', 'PM', 1621.94, 0.00, 1621.94, 'testliwat', 2, '2026-08-10 19:11:52');

-- --------------------------------------------------------

--
-- Table structure for table `space_price_history`
--

CREATE TABLE `space_price_history` (
  `id` int(11) NOT NULL,
  `space_type_id` int(11) NOT NULL,
  `old_price` decimal(10,4) DEFAULT NULL,
  `new_price` decimal(10,4) NOT NULL,
  `changed_at` datetime NOT NULL,
  `changed_by_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `space_price_history`
--

INSERT INTO `space_price_history` (`id`, `space_type_id`, `old_price`, `new_price`, `changed_at`, `changed_by_id`) VALUES
(1, 3, 4.1667, 5.0000, '2026-05-13 13:55:59', 2),
(2, 3, 5.0000, 4.1667, '2026-05-15 08:01:07', 2),
(3, 3, 4.1667, 5.0000, '2026-05-22 07:05:12', 2);

-- --------------------------------------------------------

--
-- Table structure for table `space_types`
--

CREATE TABLE `space_types` (
  `id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `rate_per_minute` decimal(10,4) DEFAULT NULL,
  `description` varchar(255) DEFAULT NULL,
  `capacity` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `space_types`
--

INSERT INTO `space_types` (`id`, `name`, `rate_per_minute`, `description`, `capacity`) VALUES
(1, 'Regular Lounge', 0.1667, NULL, 20),
(2, 'Premium Lounge', 0.3333, NULL, 30),
(3, 'Boardroom', 5.0000, NULL, NULL);

-- --------------------------------------------------------

--
-- Table structure for table `staff_attendance`
--

CREATE TABLE `staff_attendance` (
  `id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `time_in` datetime NOT NULL,
  `time_out` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `staff_attendance`
--

INSERT INTO `staff_attendance` (`id`, `user_id`, `time_in`, `time_out`) VALUES
(2, 2, '2026-04-28 11:41:47', '2026-04-28 13:26:58'),
(4, 2, '2026-04-28 13:27:17', '2026-04-28 13:45:43'),
(6, 2, '2026-04-28 13:50:46', '2026-04-28 14:03:21'),
(8, 2, '2026-04-28 14:04:53', '2026-04-28 14:20:56'),
(9, 2, '2026-04-29 13:48:36', '2026-04-29 14:19:05'),
(10, 2, '2026-04-29 14:19:07', '2026-04-29 14:19:12'),
(11, 2, '2026-04-29 14:19:37', '2026-04-29 14:21:27'),
(13, 2, '2026-05-01 14:17:39', '2026-05-01 14:32:41'),
(15, 2, '2026-05-06 13:48:01', '2026-05-26 08:18:01'),
(16, 2, '2026-05-07 12:49:33', '2026-05-07 13:10:51'),
(19, 2, '2026-05-07 13:11:33', '2026-05-07 13:11:55'),
(20, 2, '2026-05-08 11:57:41', '2026-05-26 08:18:01'),
(21, 2, '2026-05-08 11:59:56', '2026-05-26 08:18:01'),
(23, 2, '2026-05-08 14:44:22', '2026-05-08 14:57:53'),
(25, 2, '2026-05-08 14:58:06', '2026-05-08 15:05:38'),
(26, 2, '2026-05-08 15:05:44', '2026-05-08 15:06:18'),
(28, 2, '2026-05-08 15:06:46', '2026-05-08 15:13:04'),
(30, 2, '2026-05-10 08:12:04', '2026-05-26 08:18:01'),
(31, 2, '2026-05-10 08:12:31', '2026-05-26 08:18:01'),
(32, 2, '2026-05-10 08:15:28', '2026-05-26 08:18:01'),
(33, 2, '2026-05-10 08:52:53', '2026-05-26 08:18:01'),
(34, 2, '2026-05-10 09:27:49', '2026-05-10 09:51:59'),
(35, 2, '2026-05-10 10:05:06', '2026-05-26 08:18:01'),
(36, 2, '2026-05-10 10:05:07', '2026-05-26 08:18:01'),
(37, 2, '2026-05-10 10:11:24', '2026-05-26 08:18:01'),
(38, 2, '2026-05-10 10:11:26', '2026-05-10 10:18:01'),
(39, 2, '2026-05-10 10:18:30', '2026-05-26 08:18:01'),
(40, 2, '2026-05-12 07:09:24', '2026-05-26 08:18:01'),
(41, 2, '2026-05-12 07:25:36', '2026-05-26 08:18:01'),
(42, 2, '2026-05-12 07:25:41', '2026-05-12 07:38:52'),
(43, 2, '2026-05-12 07:38:59', '2026-05-26 08:18:01'),
(44, 2, '2026-05-12 08:00:29', '2026-05-12 08:01:05'),
(46, 2, '2026-05-12 08:10:41', '2026-05-26 08:18:01'),
(47, 2, '2026-05-12 08:30:39', '2026-05-26 08:18:01'),
(48, 2, '2026-05-12 12:16:02', '2026-05-12 12:44:10'),
(49, 2, '2026-05-12 12:42:48', '2026-05-26 08:18:01'),
(51, 2, '2026-05-12 13:07:12', '2026-05-12 13:09:59'),
(52, 2, '2026-05-13 13:23:03', '2026-05-26 08:18:01'),
(54, 2, '2026-05-13 13:44:05', '2026-05-13 14:21:45'),
(55, 2, '2026-05-13 14:21:49', '2026-05-13 14:24:59'),
(56, 2, '2026-05-13 14:28:09', '2026-05-13 14:28:22'),
(57, 2, '2026-05-14 07:29:28', '2026-05-26 08:18:01'),
(58, 2, '2026-05-14 08:00:05', '2026-05-14 08:00:38'),
(61, 2, '2026-05-14 08:40:24', '2026-05-26 08:18:01'),
(62, 2, '2026-05-15 08:00:39', '2026-05-26 08:18:01'),
(63, 2, '2026-05-15 09:57:54', '2026-05-26 08:18:01'),
(64, 2, '2026-05-15 09:58:26', '2026-05-26 08:18:01'),
(65, 2, '2026-05-15 12:06:40', '2026-05-15 12:16:32'),
(67, 2, '2026-05-17 13:32:09', '2026-05-26 08:18:01'),
(68, 2, '2026-05-18 04:34:10', '2026-05-26 08:18:01'),
(69, 2, '2026-05-18 04:37:25', '2026-05-26 08:18:01'),
(70, 2, '2026-05-18 05:03:40', '2026-05-26 08:18:01'),
(71, 2, '2026-05-18 05:09:46', '2026-05-26 08:18:01'),
(72, 2, '2026-05-18 05:16:45', '2026-05-26 08:18:01'),
(73, 2, '2026-05-18 05:18:55', '2026-05-26 08:18:01'),
(74, 2, '2026-05-18 05:23:31', '2026-05-26 08:18:01'),
(75, 2, '2026-05-18 05:23:32', '2026-05-18 05:31:05'),
(76, 2, '2026-05-18 05:56:42', '2026-05-18 05:58:40'),
(79, 2, '2026-05-18 13:47:15', '2026-05-26 08:18:01'),
(80, 2, '2026-05-18 13:54:00', '2026-05-26 08:18:01'),
(81, 2, '2026-05-18 13:56:29', '2026-05-26 08:18:01'),
(82, 2, '2026-05-18 14:04:14', '2026-05-26 08:18:01'),
(83, 2, '2026-05-18 14:16:22', '2026-05-26 08:18:01'),
(85, 2, '2026-05-18 14:34:15', '2026-05-26 08:18:01'),
(87, 2, '2026-05-18 14:38:09', '2026-05-26 08:18:01'),
(89, 2, '2026-05-18 15:01:35', '2026-05-18 16:54:20'),
(90, 2, '2026-05-18 16:54:50', '2026-05-18 16:55:06'),
(91, 2, '2026-05-18 16:56:41', '2026-05-18 16:59:04'),
(92, 2, '2026-05-19 13:00:14', '2026-05-26 08:18:01'),
(93, 2, '2026-05-19 13:00:55', '2026-05-19 13:01:03'),
(94, 2, '2026-05-19 14:40:42', '2026-05-26 08:18:01'),
(95, 2, '2026-05-19 14:40:43', '2026-05-26 08:18:01'),
(98, 2, '2026-05-19 15:27:01', '2026-05-19 15:30:10'),
(100, 2, '2026-05-19 15:31:45', '2026-05-26 08:18:01'),
(101, 2, '2026-05-20 05:23:15', '2026-05-20 05:36:09'),
(104, 2, '2026-05-20 05:39:21', '2026-05-20 05:39:33'),
(105, 2, '2026-05-20 06:08:34', '2026-05-20 06:47:14'),
(106, 2, '2026-05-20 06:47:41', '2026-05-26 08:18:01'),
(107, 2, '2026-05-20 12:06:17', '2026-05-20 12:12:40'),
(108, 2, '2026-05-20 12:12:44', '2026-05-20 12:22:59'),
(109, 2, '2026-05-20 12:24:35', '2026-05-26 08:18:01'),
(110, 2, '2026-05-20 13:01:38', '2026-05-20 13:15:45'),
(111, 2, '2026-05-20 13:42:40', '2026-05-20 13:55:19'),
(112, 2, '2026-05-20 14:13:52', '2026-05-20 14:17:39'),
(113, 2, '2026-05-20 14:17:48', '2026-05-26 08:18:01'),
(114, 2, '2026-05-21 13:17:28', '2026-05-21 13:24:01'),
(115, 2, '2026-05-21 13:35:18', '2026-05-21 13:56:25'),
(116, 2, '2026-05-21 13:56:28', '2026-05-21 13:56:38'),
(117, 2, '2026-05-21 14:19:05', '2026-05-21 14:22:05'),
(118, 2, '2026-05-21 14:22:30', '2026-05-21 14:22:39'),
(119, 2, '2026-05-21 14:23:02', '2026-05-21 14:23:15'),
(120, 2, '2026-05-21 14:25:17', '2026-05-21 14:39:34'),
(121, 2, '2026-05-21 14:41:06', '2026-05-21 14:45:29'),
(122, 2, '2026-05-21 14:45:54', '2026-05-26 08:18:01'),
(123, 2, '2026-05-22 06:11:16', '2026-05-22 06:43:46'),
(129, 2, '2026-05-22 06:44:27', '2026-05-22 06:45:19'),
(131, 2, '2026-05-22 06:47:36', '2026-05-22 06:53:11'),
(132, 2, '2026-05-22 06:55:20', '2026-05-22 07:02:31'),
(133, 2, '2026-05-22 07:04:10', '2026-05-22 07:27:00'),
(136, 2, '2026-05-22 07:31:26', '2026-05-22 07:32:29'),
(139, 2, '2026-05-22 07:32:52', '2026-05-26 08:18:01'),
(140, 2, '2026-05-22 07:38:23', '2026-05-26 08:18:01'),
(141, 2, '2026-05-22 08:15:54', '2026-05-22 08:15:59'),
(142, 2, '2026-05-22 08:16:56', '2026-05-26 08:18:01'),
(143, 2, '2026-05-22 08:23:57', '2026-05-22 08:26:50'),
(146, 2, '2026-05-26 06:02:14', '2026-05-26 08:18:01'),
(147, 2, '2026-05-26 06:02:19', '2026-05-26 08:18:01'),
(150, 2, '2026-05-26 08:18:01', '2026-05-26 14:43:13'),
(151, 2, '2026-05-26 14:43:13', '2026-05-26 14:45:53'),
(155, 2, '2026-05-26 15:17:02', '2026-05-26 15:18:07'),
(156, 2, '2026-05-26 15:18:07', '2026-05-26 15:29:22'),
(157, 2, '2026-05-26 15:38:20', '2026-05-26 15:46:05'),
(158, 2, '2026-05-26 15:46:05', '2026-05-26 17:08:13'),
(159, 2, '2026-05-26 17:08:13', '2026-05-26 17:36:30'),
(161, 2, '2026-05-26 17:41:09', '2026-05-26 17:41:35'),
(162, 2, '2026-05-28 12:56:45', '2026-05-28 13:26:31'),
(163, 2, '2026-05-28 13:26:35', '2026-05-28 13:37:52'),
(164, 2, '2026-05-28 13:37:52', '2026-05-28 13:41:18'),
(165, 2, '2026-05-28 13:55:19', '2026-05-28 14:14:27'),
(167, 2, '2026-05-28 14:14:27', '2026-05-28 14:40:18'),
(168, 2, '2026-05-28 14:40:18', '2026-05-28 14:45:31'),
(169, 2, '2026-05-28 14:45:31', '2026-05-28 14:55:25'),
(170, 2, '2026-05-29 12:59:22', '2026-05-29 13:04:16'),
(171, 2, '2026-05-29 13:04:16', '2026-05-29 13:05:50'),
(172, 2, '2026-05-29 13:05:50', '2026-05-29 13:05:51'),
(173, 2, '2026-05-29 13:05:51', '2026-05-29 13:05:52'),
(174, 2, '2026-05-29 13:05:52', '2026-05-29 13:15:24'),
(175, 2, '2026-05-29 13:15:24', '2026-05-29 13:38:06'),
(176, 2, '2026-05-29 13:38:06', '2026-05-29 13:46:23'),
(178, 2, '2026-06-02 06:40:46', '2026-06-02 06:42:32'),
(179, 2, '2026-06-02 06:42:32', '2026-06-02 06:43:09'),
(183, 2, '2026-06-02 07:07:00', '2026-06-02 07:15:35'),
(187, 2, '2026-06-02 08:15:17', '2026-06-02 08:16:44'),
(188, 2, '2026-06-02 09:06:23', '2026-06-02 09:06:42'),
(189, 2, '2026-06-02 13:09:12', '2026-06-02 13:23:58'),
(190, 2, '2026-06-02 13:24:00', '2026-06-02 13:38:54'),
(193, 2, '2026-06-02 13:50:50', '2026-06-29 08:22:26'),
(194, 2, '2026-06-29 08:22:26', '2026-06-29 09:43:56'),
(196, 2, '2026-07-20 12:43:36', '2026-07-20 12:54:34'),
(197, 2, '2026-07-20 12:54:34', '2026-07-20 13:17:51'),
(198, 2, '2026-07-20 13:18:08', '2026-07-20 13:18:18'),
(199, 2, '2026-07-20 13:18:18', '2026-07-20 14:50:49'),
(200, 2, '2026-07-22 12:24:18', '2026-07-22 12:26:24'),
(201, 2, '2026-07-22 12:26:24', '2026-07-22 12:26:24'),
(202, 2, '2026-07-22 12:26:24', '2026-07-22 12:26:24'),
(203, 2, '2026-07-22 12:26:24', '2026-07-22 12:26:26'),
(204, 2, '2026-07-22 12:26:26', '2026-07-22 12:26:26'),
(205, 2, '2026-07-22 12:26:26', '2026-07-22 12:39:56'),
(206, 2, '2026-07-22 12:39:56', '2026-07-22 14:11:10'),
(207, 2, '2026-07-22 14:11:10', '2026-07-22 14:27:25'),
(208, 2, '2026-07-22 14:27:25', '2026-07-22 16:28:37'),
(209, 2, '2026-07-22 16:28:58', '2026-07-22 16:29:18'),
(211, 2, '2026-08-09 15:45:53', '2026-08-09 15:47:20'),
(213, 2, '2026-08-09 16:02:46', '2026-08-09 16:12:36'),
(214, 2, '2026-08-09 16:12:36', '2026-08-09 16:22:32'),
(215, 2, '2026-08-09 16:22:32', '2026-08-09 16:22:57'),
(216, 2, '2026-08-09 16:23:11', '2026-08-09 16:31:38'),
(218, 2, '2026-08-09 16:31:47', '2026-08-09 16:32:18'),
(219, 22, '2026-08-10 16:23:14', '2026-08-10 16:27:00'),
(220, 22, '2026-08-10 19:45:24', '2026-08-10 19:58:34'),
(221, 22, '2026-08-10 19:59:15', NULL);

-- --------------------------------------------------------

--
-- Table structure for table `staff_performance_logs`
--

CREATE TABLE `staff_performance_logs` (
  `id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `shift_date` date NOT NULL,
  `orders_handled` int(11) NOT NULL,
  `avg_order_minutes` decimal(8,2) NOT NULL,
  `sessions_managed` int(11) NOT NULL,
  `upsell_count` int(11) NOT NULL,
  `admin_note` text DEFAULT NULL,
  `score` decimal(10,2) NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `customers_served` int(11) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `staff_performance_logs`
--

INSERT INTO `staff_performance_logs` (`id`, `user_id`, `shift_date`, `orders_handled`, `avg_order_minutes`, `sessions_managed`, `upsell_count`, `admin_note`, `score`, `created_at`, `customers_served`) VALUES
(1, 2, '2026-05-08', 1, 1.00, 1, 0, 'smoke', 2.90, '2026-05-08 14:42:25', 0),
(2, 2, '2026-05-08', 1, 1.00, 1, 0, 'smoke', 2.90, '2026-05-08 15:02:49', 0),
(3, 2, '2026-05-08', 1, 1.00, 1, 0, 'smoke', 2.90, '2026-05-08 15:06:17', 0),
(5, 2, '2026-05-08', 0, 0.00, 0, 0, 'smoke', 0.00, '2026-05-21 14:17:57', 0),
(6, 2, '2026-05-08', 0, 0.00, 0, 0, 'smoke', 0.00, '2026-05-21 14:44:44', 0),
(8, 2, '2026-05-08', 0, 0.00, 0, 0, 'smoke', 0.00, '2026-05-28 13:00:46', 0),
(9, 2, '2026-05-08', 0, 0.00, 0, 0, 'smoke', 0.00, '2026-05-28 13:20:16', 0),
(10, 2, '2026-05-08', 0, 0.00, 0, 0, 'smoke', 0.00, '2026-06-02 08:29:59', 0);

-- --------------------------------------------------------

--
-- Table structure for table `transactions`
--

CREATE TABLE `transactions` (
  `id` int(11) NOT NULL,
  `session_id` int(11) NOT NULL,
  `time_bill` decimal(10,2) NOT NULL,
  `food_bill` decimal(10,2) NOT NULL,
  `total_bill` decimal(10,2) NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `payment_method` varchar(50) NOT NULL DEFAULT 'cash',
  `amount_tendered` decimal(10,2) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `transactions`
--

INSERT INTO `transactions` (`id`, `session_id`, `time_bill`, `food_bill`, `total_bill`, `created_at`, `payment_method`, `amount_tendered`) VALUES
(7, 7, 9.25, 185.00, 194.25, '2026-05-06 14:16:49', 'cash', NULL),
(8, 8, 5.24, 325.00, 330.24, '2026-05-07 13:10:26', 'cash', NULL),
(9, 10, 43.16, 420.00, 463.16, '2026-05-08 12:13:08', 'cash', NULL),
(10, 9, 44.78, 665.00, 709.78, '2026-05-08 12:13:11', 'cash', NULL),
(11, 11, 3.82, 530.00, 533.82, '2026-05-08 14:57:23', 'cash', NULL),
(12, 12, 28.40, 0.00, 28.40, '2026-05-10 09:51:31', 'cash', NULL),
(13, 13, 901.29, 945.00, 1846.29, '2026-05-12 07:10:12', 'cash', NULL),
(14, 14, 11.61, 1540.00, 1551.61, '2026-05-12 08:39:30', 'cash', NULL),
(15, 17, 195.03, 250.00, 445.03, '2026-05-18 05:30:28', 'cash', NULL),
(16, 16, 214.80, 105.00, 319.80, '2026-05-18 15:18:56', 'cash', NULL),
(17, 18, 0.14, 425.00, 425.14, '2026-05-18 15:19:48', 'cash', NULL),
(18, 15, 1465.98, 400.00, 1865.98, '2026-05-18 15:28:35', 'gcash', NULL),
(19, 19, 1.54, 300.00, 301.54, '2026-05-18 15:36:08', 'gcash', NULL),
(20, 20, 0.14, 210.00, 210.14, '2026-05-18 16:17:45', 'gcash', NULL),
(21, 22, 0.34, 555.00, 555.34, '2026-05-20 12:10:29', 'gcash', NULL),
(22, 23, 5604.46, 795.00, 6399.46, '2026-05-21 13:18:13', 'gcash', NULL),
(23, 24, 0.26, 75.00, 75.26, '2026-05-22 06:43:19', 'cash', NULL),
(24, 25, 958.20, 0.00, 958.20, '2026-05-26 06:55:49', 'gcash', NULL),
(25, 21, 3204.39, 400.00, 3604.39, '2026-05-26 06:56:06', 'cash', NULL),
(26, 26, 0.93, 220.00, 220.93, '2026-05-26 17:39:39', 'gcash', NULL),
(27, 27, 0.71, 149.00, 149.71, '2026-05-28 13:33:45', 'bdo', NULL),
(28, 28, 12.61, 209.00, 221.61, '2026-05-28 14:39:17', 'bpi', NULL),
(29, 29, 3.24, 179.00, 182.24, '2026-05-28 14:40:09', 'gcash', NULL),
(30, 30, 1.33, 1051.00, 1052.33, '2026-05-28 14:46:38', 'cash', NULL),
(31, 31, 15229.94, 772.98, 16002.92, '2026-06-29 08:23:00', 'gcash', NULL),
(32, 32, 6491.37, 119.00, 6610.37, '2026-06-29 08:23:04', 'bdo', NULL),
(33, 33, 471.10, 110.00, 581.10, '2026-07-22 12:36:05', 'gcash', NULL),
(34, 34, 4346.13, 199.00, 4545.13, '2026-08-09 15:34:02', 'bpi', NULL),
(35, 35, 65.25, 363.00, 428.25, '2026-08-09 16:30:39', 'cash', 500.00),
(36, 36, 1.73, 473.00, 474.73, '2026-08-10 16:17:18', 'cash', 500.00),
(37, 37, 0.86, 593.00, 593.86, '2026-08-10 16:26:08', 'cash', 600.00),
(38, 38, 0.15, 159.00, 159.15, '2026-08-10 16:26:53', 'gcash', NULL),
(39, 39, 0.20, 394.00, 394.20, '2026-08-10 18:03:40', 'cash', 500.00),
(40, 40, 0.60, 339.00, 339.60, '2026-08-10 19:23:11', 'cash', 500.00),
(41, 41, 8.35, 140.00, 148.35, '2026-08-10 19:45:33', 'gcash', NULL),
(42, 42, 8.22, 145.00, 153.22, '2026-08-10 19:45:36', 'bdo', NULL),
(43, 43, 7.94, 110.00, 117.94, '2026-08-10 19:45:39', 'bpi', NULL),
(44, 45, 2.37, 0.00, 2.37, '2026-08-10 20:01:42', 'cash', 100.00);

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int(11) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `username` varchar(50) NOT NULL,
  `password` varchar(255) NOT NULL,
  `role` varchar(20) NOT NULL,
  `job_role` varchar(50) NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `failed_login_attempts` int(11) DEFAULT 0,
  `locked_until` datetime DEFAULT NULL,
  `last_login` datetime DEFAULT NULL,
  `password_changed_at` datetime DEFAULT current_timestamp(),
  `is_active` tinyint(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `full_name`, `username`, `password`, `role`, `job_role`, `created_at`, `failed_login_attempts`, `locked_until`, `last_login`, `password_changed_at`, `is_active`) VALUES
(2, 'Admin', 'admin', '$2b$12$D6B4Qe54/QcA/TD.gYwzXeTZwjSO8Lq.8Un0ykNjEXNPx3LB//VJu', 'admin', 'admin', '2026-04-28 11:41:20', 0, NULL, '2026-08-09 16:31:47', '2026-05-21 14:06:50', 0),
(22, 'Clark Kent', 'Superman', '$2b$12$TJ8CLREQPkaUdRYjbe2YG.dNYBMlZV.xpCMw/ZqfrkqGITNJS.wMm', 'staff', 'cashier', '2026-08-10 16:23:01', 0, NULL, '2026-08-10 19:59:15', '2026-08-10 16:23:01', 1);

--
-- Indexes for dumped tables
--

--
-- Indexes for table `admins`
--
ALTER TABLE `admins`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `username` (`username`);

--
-- Indexes for table `boardroom_bookings`
--
ALTER TABLE `boardroom_bookings`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_bookings_status_end` (`status`,`expected_end_at`);

--
-- Indexes for table `customer_sessions`
--
ALTER TABLE `customer_sessions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `space_type_id` (`space_type_id`),
  ADD KEY `idx_customer_sessions_time_in` (`time_in`);

--
-- Indexes for table `daily_sales_reports`
--
ALTER TABLE `daily_sales_reports`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `report_date` (`report_date`),
  ADD KEY `generated_by` (`generated_by`);

--
-- Indexes for table `expenses`
--
ALTER TABLE `expenses`
  ADD PRIMARY KEY (`id`),
  ADD KEY `logged_by` (`logged_by`);

--
-- Indexes for table `finance_budgets`
--
ALTER TABLE `finance_budgets`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `finance_transactions`
--
ALTER TABLE `finance_transactions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `budget_id` (`budget_id`);

--
-- Indexes for table `inventory_items`
--
ALTER TABLE `inventory_items`
  ADD PRIMARY KEY (`id`),
  ADD KEY `menu_item_id` (`menu_item_id`);

--
-- Indexes for table `inventory_logs`
--
ALTER TABLE `inventory_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `inventory_item_id` (`inventory_item_id`),
  ADD KEY `changed_by` (`changed_by`);

--
-- Indexes for table `lounge_bookings`
--
ALTER TABLE `lounge_bookings`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `menu_categories`
--
ALTER TABLE `menu_categories`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indexes for table `menu_items`
--
ALTER TABLE `menu_items`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `menu_item_ingredients`
--
ALTER TABLE `menu_item_ingredients`
  ADD PRIMARY KEY (`id`),
  ADD KEY `menu_item_id` (`menu_item_id`),
  ADD KEY `ingredient_item_id` (`ingredient_item_id`);

--
-- Indexes for table `orders`
--
ALTER TABLE `orders`
  ADD PRIMARY KEY (`id`),
  ADD KEY `handled_by` (`handled_by`),
  ADD KEY `idx_orders_session_status` (`customer_session_id`,`status`,`id`);

--
-- Indexes for table `order_items`
--
ALTER TABLE `order_items`
  ADD PRIMARY KEY (`id`),
  ADD KEY `menu_item_id` (`menu_item_id`),
  ADD KEY `idx_order_items_order_id` (`order_id`);

--
-- Indexes for table `payables`
--
ALTER TABLE `payables`
  ADD PRIMARY KEY (`id`),
  ADD KEY `created_by` (`created_by`);

--
-- Indexes for table `receivables`
--
ALTER TABLE `receivables`
  ADD PRIMARY KEY (`id`),
  ADD KEY `created_by` (`created_by`),
  ADD KEY `session_id` (`session_id`);

--
-- Indexes for table `soft_balance_entries`
--
ALTER TABLE `soft_balance_entries`
  ADD PRIMARY KEY (`id`),
  ADD KEY `generated_by` (`generated_by`),
  ADD KEY `ix_soft_balance_entries_balance_date` (`balance_date`);

--
-- Indexes for table `space_price_history`
--
ALTER TABLE `space_price_history`
  ADD PRIMARY KEY (`id`),
  ADD KEY `space_type_id` (`space_type_id`),
  ADD KEY `changed_by_id` (`changed_by_id`);

--
-- Indexes for table `space_types`
--
ALTER TABLE `space_types`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indexes for table `staff_attendance`
--
ALTER TABLE `staff_attendance`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user_id` (`user_id`);

--
-- Indexes for table `staff_performance_logs`
--
ALTER TABLE `staff_performance_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user_id` (`user_id`);

--
-- Indexes for table `transactions`
--
ALTER TABLE `transactions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `session_id` (`session_id`),
  ADD KEY `idx_transactions_created_at` (`created_at`),
  ADD KEY `idx_transactions_payment_method` (`payment_method`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `username` (`username`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `admins`
--
ALTER TABLE `admins`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- AUTO_INCREMENT for table `boardroom_bookings`
--
ALTER TABLE `boardroom_bookings`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=13;

--
-- AUTO_INCREMENT for table `customer_sessions`
--
ALTER TABLE `customer_sessions`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=46;

--
-- AUTO_INCREMENT for table `daily_sales_reports`
--
ALTER TABLE `daily_sales_reports`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=33;

--
-- AUTO_INCREMENT for table `expenses`
--
ALTER TABLE `expenses`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=45;

--
-- AUTO_INCREMENT for table `finance_budgets`
--
ALTER TABLE `finance_budgets`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- AUTO_INCREMENT for table `finance_transactions`
--
ALTER TABLE `finance_transactions`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=12;

--
-- AUTO_INCREMENT for table `inventory_items`
--
ALTER TABLE `inventory_items`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=77;

--
-- AUTO_INCREMENT for table `inventory_logs`
--
ALTER TABLE `inventory_logs`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=64;

--
-- AUTO_INCREMENT for table `lounge_bookings`
--
ALTER TABLE `lounge_bookings`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `menu_categories`
--
ALTER TABLE `menu_categories`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=6;

--
-- AUTO_INCREMENT for table `menu_items`
--
ALTER TABLE `menu_items`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=150;

--
-- AUTO_INCREMENT for table `menu_item_ingredients`
--
ALTER TABLE `menu_item_ingredients`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=18;

--
-- AUTO_INCREMENT for table `orders`
--
ALTER TABLE `orders`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=60;

--
-- AUTO_INCREMENT for table `order_items`
--
ALTER TABLE `order_items`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=133;

--
-- AUTO_INCREMENT for table `payables`
--
ALTER TABLE `payables`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=28;

--
-- AUTO_INCREMENT for table `receivables`
--
ALTER TABLE `receivables`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=39;

--
-- AUTO_INCREMENT for table `soft_balance_entries`
--
ALTER TABLE `soft_balance_entries`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=67;

--
-- AUTO_INCREMENT for table `space_price_history`
--
ALTER TABLE `space_price_history`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `space_types`
--
ALTER TABLE `space_types`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `staff_attendance`
--
ALTER TABLE `staff_attendance`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=222;

--
-- AUTO_INCREMENT for table `staff_performance_logs`
--
ALTER TABLE `staff_performance_logs`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=11;

--
-- AUTO_INCREMENT for table `transactions`
--
ALTER TABLE `transactions`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=45;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=23;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `customer_sessions`
--
ALTER TABLE `customer_sessions`
  ADD CONSTRAINT `customer_sessions_ibfk_1` FOREIGN KEY (`space_type_id`) REFERENCES `space_types` (`id`);

--
-- Constraints for table `daily_sales_reports`
--
ALTER TABLE `daily_sales_reports`
  ADD CONSTRAINT `daily_sales_reports_ibfk_1` FOREIGN KEY (`generated_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `expenses`
--
ALTER TABLE `expenses`
  ADD CONSTRAINT `expenses_ibfk_1` FOREIGN KEY (`logged_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `finance_transactions`
--
ALTER TABLE `finance_transactions`
  ADD CONSTRAINT `finance_transactions_ibfk_1` FOREIGN KEY (`budget_id`) REFERENCES `finance_budgets` (`id`);

--
-- Constraints for table `inventory_items`
--
ALTER TABLE `inventory_items`
  ADD CONSTRAINT `inventory_items_ibfk_1` FOREIGN KEY (`menu_item_id`) REFERENCES `menu_items` (`id`);

--
-- Constraints for table `inventory_logs`
--
ALTER TABLE `inventory_logs`
  ADD CONSTRAINT `inventory_logs_ibfk_1` FOREIGN KEY (`inventory_item_id`) REFERENCES `inventory_items` (`id`),
  ADD CONSTRAINT `inventory_logs_ibfk_2` FOREIGN KEY (`changed_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `menu_item_ingredients`
--
ALTER TABLE `menu_item_ingredients`
  ADD CONSTRAINT `menu_item_ingredients_ibfk_1` FOREIGN KEY (`menu_item_id`) REFERENCES `menu_items` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `menu_item_ingredients_ibfk_2` FOREIGN KEY (`ingredient_item_id`) REFERENCES `menu_items` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `orders`
--
ALTER TABLE `orders`
  ADD CONSTRAINT `orders_ibfk_1` FOREIGN KEY (`customer_session_id`) REFERENCES `customer_sessions` (`id`),
  ADD CONSTRAINT `orders_ibfk_2` FOREIGN KEY (`handled_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `order_items`
--
ALTER TABLE `order_items`
  ADD CONSTRAINT `order_items_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`),
  ADD CONSTRAINT `order_items_ibfk_2` FOREIGN KEY (`menu_item_id`) REFERENCES `menu_items` (`id`);

--
-- Constraints for table `payables`
--
ALTER TABLE `payables`
  ADD CONSTRAINT `payables_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `receivables`
--
ALTER TABLE `receivables`
  ADD CONSTRAINT `receivables_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `receivables_ibfk_2` FOREIGN KEY (`session_id`) REFERENCES `customer_sessions` (`id`);

--
-- Constraints for table `soft_balance_entries`
--
ALTER TABLE `soft_balance_entries`
  ADD CONSTRAINT `soft_balance_entries_ibfk_1` FOREIGN KEY (`generated_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `space_price_history`
--
ALTER TABLE `space_price_history`
  ADD CONSTRAINT `space_price_history_ibfk_1` FOREIGN KEY (`space_type_id`) REFERENCES `space_types` (`id`),
  ADD CONSTRAINT `space_price_history_ibfk_2` FOREIGN KEY (`changed_by_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `staff_attendance`
--
ALTER TABLE `staff_attendance`
  ADD CONSTRAINT `staff_attendance_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `staff_performance_logs`
--
ALTER TABLE `staff_performance_logs`
  ADD CONSTRAINT `staff_performance_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `transactions`
--
ALTER TABLE `transactions`
  ADD CONSTRAINT `transactions_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `customer_sessions` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
