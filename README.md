# ![Logo](https://github.com/jampez77/Ryanair/blob/main/logo.png "Ryanair Logo") Ryanair API for Home Assistant

This component will allow you to bring your upcoming Ryanair flight information into [Home Assistant](https://www.home-assistant.io/). Each flight will provide the following information:

* Flight Number.
* Origin / Destination Airport code.
* Check in open / close time.
* Arrival / departure time.
* Passengers name and seat number.
* Mobile frienldy boarding passes.
* number of upcoming flights.
* flight cancellation status.

This project is very much a work in progress and there are still many issue that need addressing. If you have the skills, time and implication then please feel free to contribute.


---

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE.md)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![Project Maintenance][maintenance-shield]


Enjoying this? Help me out with a :beers: or :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/jampez77)


## Installation through [HACS](https://hacs.xyz/)
Use [HACS](https://hacs.xyz/) to install the **Ryanair** integration.

## Manual Installation
Use this route only if you do not want to use [HACS](https://hacs.xyz/) and love the pain of manually installing regular updates.
* Add the `ryanair` folder in your `custom_components` folder

## Usage

Once installed, login with your Ryanair credentials (Social sign in is not supported!). If this is the first time logging in via this integration then you will have 10 minutes to enter the MFA code that is sent to your Ryanair email address.

---

[commits-shield]: https://img.shields.io/github/commit-activity/y/jampez77/Ryanairs.svg?style=for-the-badge
[commits]: https://github.com/jampez77/Ryanair/commits/main
[license-shield]: https://img.shields.io/github/license/jampez77/Ryanair.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/Maintainer-Jamie%20Nandhra--Pezone-blue
[releases-shield]: https://img.shields.io/github/v/release/jampez77/Ryanair.svg?style=for-the-badge
[releases]: https://github.com/jampez77/Ryanair/releases 
