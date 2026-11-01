#include "core/device_presence.hpp"
#include <iostream>
#include <stdexcept>
using Gate = sl3::DevicePresence;
using State = Gate::State;
void require(bool value) { if(!value) throw std::runtime_error("Presence readiness policy failed"); }
int main() {
    try {
        Gate transient(100,2000);
        require(transient.observe(0,100)==State::waiting && transient.sleep_ms()==25);
        require(transient.observe(0,2080)==State::waiting && transient.sleep_ms()==20);
        require(transient.observe(1,2099)==State::ready && transient.sleep_ms()==0);
        require(transient.observe(0,2100)==State::ready);
        for(unsigned matches : {0u,1u}) {
            Gate late(100,2000);
            require(late.observe(matches,2100)==State::expired);
            require(late.observe(1,2101)==State::expired && late.sleep_ms()==0);
        }
        Gate multiple(100,2000);
        require(multiple.observe(0,100)==State::waiting);
        require(multiple.observe(2,101)==State::ambiguous);
        require(multiple.observe(1,102)==State::ambiguous);
        Gate rollback(100,2000);
        require(rollback.observe(0,101)==State::waiting);
        require(rollback.observe(1,100)==State::invalid);
        Gate absent(100,0), immediate(100,0), invalid(100,2001);
        require(absent.observe(0,100)==State::absent);
        require(absent.observe(1,100)==State::absent);
        require(immediate.observe(1,100)==State::ready);
        require(invalid.observe(1,100)==State::invalid);
        std::cout << "Bounded enumeration readiness passed\n";
        return 0;
    } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
